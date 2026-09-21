"""W4: the HTTP layer between an uploaded clip and a real Modal GPU job.

Deliberately thin. This process never touches CUDA/torch/pymomentum -- it
only talks to Modal's control plane (spawn a Function, read/list a Volume)
and to disk for the upload's temp file, so it can run anywhere (a laptop, a
small always-on box) independent of the GPU image. The real pipeline lives in
modal_app.py + tools/process_clip.py; this file wires it to HTTP.

Object storage: **delivered bytes on Cloudflare R2, pipeline internals on Modal
Volumes.** This paragraph used to say "Volumes, not S3", and the sentence that
overturned it is its own: *"Volume reads go through Modal's client library, not
raw HTTP GET, so `/assets/{asset_id}` proxies bytes through this service."*
That proxy cannot answer a `Range:` request, so a `<video>` asking for a seek
gets a 200 with the entire body and the learner scrubbing their own clip --
DESIGN.md §7c's core interaction -- waits for the whole download. It is a
product defect, not a cost problem (docs/research/infrastructure.md decision 3;
R2's zero egress is a bonus, not the argument).

So: source video, GLBs and the materialised `MotionResult` live in R2 and
`GET /assets/{asset_id}` answers **302** to an R2 URL that honours ranges. The
`.npz` and the model weights stay on Volumes -- pipeline-internal, never
touched by a browser, and already working. The contract is untouched: an
`asset_id` is still opaque and immutable, never a signed or expiring URL *as*
the id (AnimationRef's schema comment), and this endpoint is still the separate
resolution step that comment describes. Where R2 has no copy -- a lesson built
before the move, or R2 not configured at all -- the old byte proxy still
answers, so nothing that used to work stops working. See storage.py.

Job state: see jobstore.py. `{job_id}.job-status.json` on a Volume is still
the default; `STEPWISE_JOB_BACKEND=postgres` moves the source of truth to a
`jobs` row without changing a byte of what this service serves.

Dispatch: modal.Function.lookup (this app must be `modal deploy`ed first,
see README) + .spawn() -- async, returns immediately. run_clip itself now
chains export_clip_gltf.remote() internally once reconstruction succeeds
(modal_app.py), so "dispatch run_clip, then export only if it succeeds" is
enforced inside the one spawned worker, not by this service polling and
re-dispatching.

Three things live here that are about a lesson's whole life rather than its
first two minutes:

  * **Dedupe on upload** (`POST /clips`). Fingerprint the clip; if this exact
    dance is already reconstructed, hand back the existing lesson and spend no
    GPU. See fingerprint.py for what it catches, measured.
  * **Removal** (`POST /lessons/{clip_id}/removal`). The takedown path. It
    deletes, it does not queue.
  * **Last-accessed marking**, which is the clock retention.py's sweeper runs
    on.

New external requirement: the `ffmpeg` and `ffprobe` BINARIES on PATH, for
fingerprinting. Not a Python dependency and not linked against -- invoked as a
subprocess, so no licence reaches this repo. Optional: without them the
service still runs and still dedupes byte-identical re-uploads, it just stops
catching re-encodes (and says so in the log rather than pretending).
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import modal
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

import fingerprint
import jobstore
import motion_result
import retention
import storage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages" / "motion-contract" / "python"))
from motion_contract import validate_job_status, validate_motion_result  # noqa: E402

from grounding import camera_intrinsics_from_clip, solve_grounding_for_clip  # noqa: E402 -- same dir, pure numpy

APP_NAME = "stepwise-motion"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # generous; PRD's real limit is 60s of video, not a byte count
JOINT_HIERARCHY = motion_result.JOINT_HIERARCHY
DANCER_FALLBACK_COLORS = motion_result.DANCER_FALLBACK_COLORS

uploads_volume = modal.Volume.from_name("stepwise-uploads", create_if_missing=True)
results_volume = modal.Volume.from_name("stepwise-results", create_if_missing=True)
eval_volume = modal.Volume.from_name("stepwise-eval", create_if_missing=True)

app = FastAPI(title="stepwise motion-api")

# clip_id -> unix time we last recorded an access. Purely a write-throttle for
# _touch(); losing it on restart costs one extra small Volume write.
_TOUCHED: dict[str, float] = {}


def _run_clip_fn():
    # Looked up per-call, not cached at import time: an app redeploy (new
    # code) should be picked up without restarting this service.
    return modal.Function.from_name(APP_NAME, "run_clip")


def _volume_read_json(volume: modal.Volume, path: str) -> Optional[dict]:
    try:
        buf = io.BytesIO()
        volume.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return json.loads(buf.getvalue())


def _volume_read_bytes(volume: modal.Volume, path: str) -> Optional[bytes]:
    try:
        buf = io.BytesIO()
        volume.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return buf.getvalue()


def _r2_read(key: str) -> Optional[bytes]:
    """Read a small object out of R2, or None for "not there / not configured".

    Only used for the gzipped MotionResult, which this service must parse and
    contract-validate before serving -- so it is the one delivered artifact
    that cannot simply be a 302. Everything a browser fetches directly goes
    through `GET /assets/{id}` and never lands in this process's memory.
    """
    if not storage.enabled():
        return None
    try:
        obj = storage.client().get_object(Bucket=storage.bucket(), Key=key)
        return obj["Body"].read()
    except Exception:  # noqa: BLE001 -- missing or unreachable: the Volume still has it
        return None


# ---------------------------------------------------------------------------
# POST /clips -- upload, store, dispatch. Returns immediately (spec item 2:
# .spawn(), never .remote()).
#
# Content-addressed: before spending a GPU, ask whether this exact dance has
# already been reconstructed. A reconstruction costs $0.0839 measured (solo-01,
# 19.7s, L40S) and two to four minutes of the learner's attention, and the same
# clip genuinely does get uploaded twice -- a retry, a second device, two
# friends learning the same TikTok. See fingerprint.py for what "the same
# dance" means and what it measurably does and does not catch.
#
# A hit returns the EXISTING clip_id and job_id, so both uploads land on one
# lesson. That is not only cheaper, it is what makes a takedown complete: one
# canonical entry, deleted once, and it is gone for everyone who uploaded it,
# instead of the dancer having to find every scattered copy.
#
# The line this deliberately does not cross (docs/research/rights-and-privacy.md):
# this is dedupe-on-upload only. You still upload your own clip. Nothing here
# builds a browsable or searchable index of who is in what -- no lookup by
# fingerprint, no "find this dancer", no public list. The index is keyed by
# content and readable only by this service.
# ---------------------------------------------------------------------------

class DispatchResponse(BaseModel):
    clip_id: str
    job_id: str
    # True when this upload matched an existing reconstruction and no GPU work
    # was started. The client needs no special handling -- the job it is handed
    # is already "succeeded", so the normal poll goes straight to the lesson.
    deduplicated: bool = False


def _publish_video(clip_id: str, path: str) -> None:
    """Best-effort: an R2 hiccup must not fail an upload whose bytes are safely
    on the Volume. The cost of skipping it is that this one lesson's video is
    served through the old byte proxy, without range requests -- degraded, and
    logged, rather than lost."""
    if not storage.enabled():
        return
    try:
        storage.put_file(storage.video_key(clip_id), path, "video/mp4")
    except Exception as e:  # noqa: BLE001
        print(f"[r2] could not publish video for {clip_id}: {e}")


def _find_existing(fp: dict) -> dict | None:
    """The canonical lesson for this content, if there is a usable one.

    'Usable' is checked against live state, not just the index: the entry must
    point at a job that actually succeeded and has not been taken down. A stale
    index entry therefore degrades to "reconstruct it again" -- which costs
    $0.08 -- and can never serve a lesson that is gone.
    """
    for entry in retention.read_index(results_volume):
        if not fingerprint.same_clip(entry, fp):
            continue
        clip_id, job_id = entry.get("clip_id"), entry.get("job_id")
        if not clip_id or not job_id:
            continue
        if _volume_read_json(results_volume, f"/{clip_id}.removed.json") is not None:
            continue  # taken down: never resurrect it, and never dedupe onto it
        status = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
        if status and status.get("state") == "succeeded":
            return entry
    return None


@app.post("/clips", response_model=DispatchResponse)
async def upload_clip(file: UploadFile = File(...)) -> DispatchResponse:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                os.unlink(tmp.name)
                raise HTTPException(413, "Clip is too large.")
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        fp = fingerprint.fingerprint(tmp_path)
        if not fp["frames"]:
            # Degraded, but not silently: without ffmpeg only byte-identical
            # re-uploads dedupe. Never a wrong match, just fewer matches.
            print("[dedupe] no perceptual fingerprint (ffmpeg unavailable or "
                  "decode failed) -- exact-sha256 matching only for this upload")
        existing = _find_existing(fp)
        if existing:
            print(f"[dedupe] hit: reusing {existing['clip_id']} "
                  f"(job {existing['job_id']}) -- no GPU run dispatched")
            return DispatchResponse(clip_id=existing["clip_id"],
                                    job_id=existing["job_id"], deduplicated=True)

        clip_id = uuid.uuid4().hex
        job_id = f"job_{clip_id}"  # resumable: DESIGN.md §7c's copyable link is just this job_id
        with uploads_volume.batch_upload() as batch:
            batch.put_file(tmp_path, f"/{clip_id}.mp4")
        # The video goes to R2 here rather than at export time, because these
        # bytes are already on this machine: publishing later would mean
        # reading a 5 MB object back out of a Volume for no reason. The Volume
        # copy stays -- run_clip reads its input from there, and moving that is
        # migration step 6 (presigned browser uploads), not this one.
        _publish_video(clip_id, tmp_path)
    finally:
        os.unlink(tmp_path)

    # job_id -> clip_id is needed later (retry, result-building) without
    # parsing it back out of the job_id string -- written once, here.
    jobstore.record_dispatch(results_volume, job_id, clip_id)
    retention.write_index(results_volume, retention.read_index(results_volume) + [
        dict(fp, clip_id=clip_id, job_id=job_id, created_at=time.time()),
    ])

    _run_clip_fn().spawn(clip_id=clip_id, job_id=job_id)
    return DispatchResponse(clip_id=clip_id, job_id=job_id)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} -- the polling endpoint W7's ProcessingScreen/lib/jobStatus.ts
# needs. Reads the real job-status.schema.json document run_clip wrote to the
# results Volume, unmodified (no reinterpretation, spec item 5).
# ---------------------------------------------------------------------------

def _clip_id_for(job_id: str) -> str:
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    return meta["clip_id"] if meta else job_id.removeprefix("job_")


def _refuse_if_removed(clip_id: str) -> None:
    """410 Gone, not 404, for a lesson that was taken down.

    The distinction is the honest one and also the useful one: whoever is
    holding this link deserves to know the lesson existed and was removed,
    rather than being told it never existed. 410 is exactly that status, and
    it tells caches to drop it permanently.
    """
    tomb = _volume_read_json(results_volume, f"/{clip_id}.removed.json")
    if tomb is not None:
        raise HTTPException(410, "This lesson was removed and is not coming back.")


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    doc = jobstore.read_status(results_volume, job_id, _clip_id_for)
    if doc is None:
        # Removal deletes the job-status document, so a MISSING one is the only
        # case that can be a removed lesson -- which is why the tombstone is
        # checked here and not at the top. This endpoint is polled every second
        # or so by the processing screen, and the common path (a job that is
        # genuinely running) must stay at exactly one Volume read, the way it
        # was before removal existed.
        #
        # Without this check a removed lesson would report "queued" forever:
        # the most misleading possible answer, since the thing it is waiting
        # for is never coming.
        _refuse_if_removed(_clip_id_for(job_id))
        # Not a 404: a job that was just spawned and hasn't written its first
        # "queued" doc yet is a real, valid state, not a missing job. Distinct
        # from "job_id never existed" only by convention -- this service does
        # not keep its own job registry (the results Volume is the registry).
        return {
            "schema_version": "1.0.0",
            "job_id": job_id,
            "state": "queued",
            "stage_message": "",
            "progress": None,
            "error": None,
            "retry_count": 0,
        }
    result = validate_job_status(doc)
    if not result.valid:
        # Fail loudly, not silently -- serving a contract-invalid document is
        # worse than a 500 (DESIGN.md §7h's honesty rule applies to plumbing
        # too, not just copy).
        raise HTTPException(500, f"job-status document failed contract validation: {result.errors}")
    return doc


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/retry -- spec item 5: retryable is decided here, not
# auto-retried. A genuine pipeline/export crash (retryable=true) gets a
# manual retry button in the UI that calls this; "too_many_dancers"
# (retryable=false) has nothing this endpoint can do about it -- refused.
# Deliberately NOT automatic: auto-retrying a crash means silently spending
# GPU time on the same crash again with no backoff/circuit-breaker, which is
# out of scope to build correctly right now (see report).
# ---------------------------------------------------------------------------

@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    doc = jobstore.read_status(results_volume, job_id, _clip_id_for)
    if doc is None:
        raise HTTPException(404, "Unknown job_id.")
    if doc["state"] != "failed":
        raise HTTPException(409, f"Job is '{doc['state']}', not 'failed' -- nothing to retry.")
    if not doc["error"] or not doc["error"]["retryable"]:
        raise HTTPException(409, "This failure is not retryable.")

    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    if meta is None:
        raise HTTPException(500, "No job-meta record for this job_id -- cannot recover its clip_id.")
    # A removal deletes the source video, so a retry here would burn GPU time
    # on a clip that no longer exists -- and must not put a removed lesson back
    # on its feet even if it somehow could.
    _refuse_if_removed(meta["clip_id"])

    retry_count = doc["retry_count"] + 1
    jobstore.record_retry(results_volume, job_id, meta["clip_id"], retry_count)
    _run_clip_fn().spawn(clip_id=meta["clip_id"], job_id=job_id, retry_count=retry_count)
    return {"job_id": job_id, "retry_count": retry_count}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/result -- serve the MotionResult.
#
# The assembly itself moved to motion_result.py so the GPU worker can run it
# ONCE, at export time, and store the document (modal_app.export_clip_gltf).
# That is what finally makes the npz droppable: this endpoint used to reload
# and re-derive a 61.30 MB npz on every single request, so "nothing reads the
# npz after export" was not true until now.
#
# Two paths, and the fallback is not dead code: lessons reconstructed before
# this shipped have an npz and no stored document.
# ---------------------------------------------------------------------------

@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str) -> dict:
    status = get_job_status(job_id)
    if status["state"] != "succeeded":
        raise HTTPException(409, f"Job is '{status['state']}', not 'succeeded'.")
    clip_id = _clip_id_for(job_id)
    # Checked explicitly rather than relying on get_job_status: this is the
    # endpoint that hands over the actual reconstruction, so it does not get to
    # assume some earlier call already refused. Once per lesson open, not per
    # poll, so the extra read is free where it matters.
    _refuse_if_removed(clip_id)

    stored = _r2_read(storage.motion_result_key(clip_id)) \
        or _volume_read_bytes(results_volume, f"/{clip_id}.motion-result.json.gz")
    if stored is not None:
        doc = json.loads(gzip.decompress(stored))
        # The stored document was written by whichever job first reconstructed
        # this clip. A second, deduplicated upload is handed that same job_id,
        # so this is normally a no-op -- but stamping it is cheap and keeps the
        # contract's "id of the job that produced this result" honest either way.
        doc["job_id"] = job_id
    else:
        try:
            doc = motion_result.build_motion_result(
                job_id, clip_id,
                _volume_read_bytes(results_volume, f"/{clip_id}.npz"),
                _volume_read_json(results_volume, f"/{clip_id}.export-manifest.json"),
                _volume_read_json(results_volume, f"/{clip_id}.performance.json"),
            )
        except motion_result.MotionResultUnavailable as e:
            raise HTTPException(e.status, e.detail) from e

    result = validate_motion_result(doc)
    if not result.valid:
        raise HTTPException(500, f"Assembled MotionResult failed contract validation: {result.errors}")

    _touch(clip_id)
    return doc


def _touch(clip_id: str) -> None:
    """Record that this lesson was opened, for the last-accessed expiry.

    ponytail: throttled by a plain in-process dict, so a learner reloading the
    page twenty times writes once. The cache is per-replica, so the real worst
    case is one small write per replica per day per lesson -- fine, and much
    better than a Volume write on every request. It is also best-effort: a
    failure here must never break serving a lesson, it only risks the lesson
    ageing out earlier than it should.
    """
    now = time.time()
    if now - _TOUCHED.get(clip_id, 0.0) < 86400:
        return
    try:
        retention.write_json(results_volume, retention.touch_path(clip_id), {"at": now})
        _TOUCHED[clip_id] = now
    except Exception as e:  # noqa: BLE001
        print(f"[retention] could not record access for {clip_id}: {e}")


# ---------------------------------------------------------------------------
# GET /assets/{asset_id} -- the "resolve separately at render time" endpoint
# both source_video.asset_id and AnimationRef.glb_asset_id require (schema
# comment: never a signed/expiring URL AS the id -- this endpoint IS the
# separate resolution step that comment describes).
#
# 302 to R2 when R2 has the object, because that is the only way the browser
# gets to do a real `Range:` request: the fallback below reads the whole thing
# into memory and returns one Response, so a seek in a 60-second clip pays for
# every byte of it (storage.py's docstring has the measurement and the
# reasoning). The fallback is not dead code -- lessons reconstructed before the
# move have no R2 copy, and a deployment with no R2 credentials must still
# serve. It is worse, not broken, and it says so in /health.
#
# The tombstone is checked BEFORE any URL is produced. A removal that left the
# GLB individually fetchable would not be a removal, and handing out a URL and
# then deleting the object would leave a live signed link to nothing.
# ---------------------------------------------------------------------------

@app.get("/assets/{asset_id:path}")
def get_asset(asset_id: str) -> Response:
    clip_id = storage.clip_id_for_asset(asset_id)
    if clip_id is None:
        raise HTTPException(404, "Unrecognized asset id.")
    _refuse_if_removed(clip_id)

    if storage.enabled():
        key = storage.key_for_asset(asset_id)
        try:
            if storage.exists(key):
                # 302, not 301: the URL on the other end is a presigned one
                # until a custom domain exists, and a permanently-cached
                # redirect to something that expires in six hours is a bug
                # waiting for a slow week.
                return RedirectResponse(storage.url_for(key), status_code=302)
        except Exception as e:  # noqa: BLE001 -- R2 unreachable: fall through, do not 500
            print(f"[r2] lookup failed for {asset_id}, falling back to the Volume: {e}")

    if asset_id.startswith("video:"):
        video = _volume_read_bytes(uploads_volume, f"/{clip_id}.mp4") or _volume_read_bytes(eval_volume, f"/{clip_id}.mp4")
        if video is None:
            raise HTTPException(404, "No video for this asset id.")
        return Response(content=video, media_type="video/mp4")
    # `{clip_id}_track{n}.glb`, per modal_app.export_clip_gltf.
    glb = _volume_read_bytes(results_volume, f"/{asset_id}")
    if glb is None:
        raise HTTPException(404, "No GLB for this asset id.")
    return Response(content=glb, media_type="model/gltf-binary")


# ---------------------------------------------------------------------------
# POST /lessons/{clip_id}/removal -- the takedown path.
#
# docs/research/rights-and-privacy.md section 1 and 6.1: the largest real
# exposure is not a lawsuit, it is a dancer finding their own body
# reconstructed on a site they never heard of with no way to ask for it to
# stop. This is the way to ask. It is the highest-value, lowest-cost item in
# that whole document and it must accept more than copyright complaints -- the
# person most likely to use it is the dancer, who has no copyright claim.
#
# The request IS the removal. No review queue, no 48-hour target to miss: the
# lesson goes immediately and getting it back requires contacting whoever made
# it. That is section 6.1's own "cheap resolution that does not require solving
# D5", and it is the honest shape -- a queue would mean promising a response
# time, and DESIGN.md section 7h says do not state a guarantee the code does
# not keep.
#
# **D5 (accounts) is where this would change, and is not mine to resolve.**
# With no accounts, anyone holding the lesson link can remove it. A link is a
# 128-bit uuid4, so this is not enumerable -- you have to have been given it --
# but it does mean an uploader's lesson can be removed by anyone they shared it
# with. With magic-link accounts the natural rules are: the uploader can delete
# their own outright; anyone else's request still takes it down immediately but
# becomes restorable by the uploader. Recorded in OPEN-DECISIONS.md D5/D7 as a
# dependency rather than guessed at here.
#
# Removal beats retention, always: a removed clip is gone now, not at the next
# sweep, and the tombstone means the TTL sweeper skips it forever after.
# ---------------------------------------------------------------------------

class RemovalRequest(BaseModel):
    # Free text, and deliberately not a fixed enum of legal categories: a
    # dancer saying "that's me and I don't want it up" must not have to find
    # the right box to tick. Stored on the tombstone as a category only.
    reason: str = "requested"


class RemovalResponse(BaseModel):
    clip_id: str
    removed: list[str]
    already_absent: list[str]


@app.post("/lessons/{clip_id}/removal", response_model=RemovalResponse)
def remove_lesson(clip_id: str, request: RemovalRequest | None = None) -> RemovalResponse:
    """Delete every stored byte of one lesson, now.

    Goes away: the source video, every dancer's GLB, the materialised
    MotionResult, the npz if one still exists, the export manifest, the
    performance record, the last-access marker, the job status and job meta,
    and the content fingerprint. What is left is a tombstone holding a
    timestamp and a reason word -- nothing derived from the person.

    Because uploads are deduplicated, there is exactly one canonical copy of a
    given clip, so this removes it for everyone who uploaded it rather than for
    whichever copy happened to be found.
    """
    if _volume_read_json(results_volume, f"/{clip_id}.removed.json") is not None:
        # Already gone. Idempotent and truthful rather than an error: the
        # answer to "please remove this" is the same either way.
        return RemovalResponse(clip_id=clip_id, removed=[], already_absent=[])

    job_id = f"job_{clip_id}"
    if _volume_read_json(results_volume, f"/{job_id}.job-meta.json") is None:
        # Older lessons (and the eval clips) used other job_id shapes; find it
        # rather than leaving a live job-status record pointing at deleted bytes.
        for entry in retention.read_index(results_volume):
            if entry.get("clip_id") == clip_id and entry.get("job_id"):
                job_id = entry["job_id"]
                break

    reason = (request.reason if request else "requested")[:200]
    outcome = retention.delete_clip(uploads_volume, results_volume, clip_id, job_id, reason)
    jobstore.forget(job_id)
    _TOUCHED.pop(clip_id, None)
    print(f"[removal] {clip_id}: deleted {len(outcome['deleted'])} artifacts ({reason})")
    return RemovalResponse(clip_id=clip_id, removed=outcome["deleted"],
                           already_absent=outcome["already_absent"])


@app.get("/health")
def health() -> dict:
    """What is actually wired up, for the person reading this at 2am.

    infrastructure.md §7 names the failure mode this exists to stop: *"a
    build-time environment variable that is absent produces a silently broken
    deploy, not an error."* That argued for a hard assertion at import. A hard
    assertion is wrong here, because "no R2" and "no database" are both
    supported, deliberate configurations during the migration -- failing to
    boot on them would mean the service cannot be deployed until every
    credential exists, which is exactly the blocking this whole branch avoids.
    So it fails loudly in the one place that can be read instead: this
    endpoint says which degraded mode it is in and which variable would end it.

    Never a secret value -- only which names are set. `assets` is the question
    that matters most, because `volume-proxy` is the mode where video seeking
    does not work.
    """
    return {
        "ok": True,
        "assets": "r2" if storage.enabled() else "volume-proxy",
        "assets_missing_env": storage.missing_env(),
        "assets_url_mode": "custom-domain" if os.environ.get("R2_PUBLIC_BASE_URL") else "presigned",
        "jobs": jobstore.health(),
        "dedupe": "perceptual" if fingerprint.ffmpeg_available() else "sha256-only",
    }
