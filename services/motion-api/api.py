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
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

import modal
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

import analytics
import fingerprint
import ingest
import jobstore
import milestones
import motion_result
import observability
import ratelimit
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


# Defined BEFORE _only_through_the_worker on purpose: Starlette runs the
# last-registered middleware first, so this only ever sees requests the origin
# check has already let through.
@app.middleware("http")
async def _prewarm_gpu(request: Request, call_next):
    """Start a GPU container the moment an upload or link request arrives.

    Runs before the body is read, so the L40S cold start and model load
    (~30 s, docs/research/pipeline-latency.md #2) overlap the upload transfer
    or the link fetch instead of following them. The container waits for this
    request's job under a one-off token (modal_app Reconstructor.
    run_when_handed); _dispatch_run hands it over. A request that ends without
    a job (refused, deduped, failed) tells it to stop, so it scales down after
    Modal's idle window (~$0.03). Links only pre-warm with a valid invite code,
    so a closed door costs nothing.
    """
    token = None
    if request.method == "POST" and (
            request.url.path == "/clips"
            or (request.url.path == "/clips/link"
                and ingest.invite_code_ok(request.headers.get("x-invite-code")))):
        try:
            token = uuid.uuid4().hex
            call = _reconstructor().run_when_handed.spawn(token)
            request.state.gpu_token = token
            request.state.gpu_call_id = getattr(call, "object_id", None)
        except Exception as e:  # noqa: BLE001 -- best-effort: dispatch spawns run() cold instead
            print(f"[prewarm] could not pre-warm a GPU container: {e}")
            token = None
    try:
        return await call_next(request)
    finally:
        if token and not getattr(request.state, "gpu_handed", False):
            try:
                if not _handoff().put(token, {"cancel": True}, skip_if_exists=True):
                    _handoff().pop(token, None)  # it had already given up
            except Exception as e:  # noqa: BLE001 -- it gives up by itself after HANDOFF_WAIT_S
                print(f"[prewarm] could not release the pre-warmed container: {e}")


def _handoff():
    return modal.Dict.from_name("stepwise-gpu-handoff", create_if_missing=True)


def _dispatch_run(http, **job) -> None:
    """Start run_clip for `job`: on this request's pre-warmed container if it
    is still waiting, otherwise as a fresh run() -- never both, never neither.

    First write wins (skip_if_exists) on both sides, so a container that gave
    up at the same instant is not a lost job: its "closed" is already there,
    this put fails, and run() is spawned.
    """
    state = getattr(http, "state", None)
    token = getattr(state, "gpu_token", None)
    if token:
        try:
            if _handoff().put(token, {"job": job}, skip_if_exists=True):
                http.state.gpu_handed = True
                _record_calls(job["job_id"], getattr(state, "gpu_call_id", None),
                              job.get("beats_call_id"), token)
                return
            _handoff().pop(token, None)
        except Exception as e:  # noqa: BLE001 -- the job still runs, just cold
            print(f"[prewarm] hand-off failed, spawning run(): {e}")
    call = _run_clip_fn().spawn(**job)
    _record_calls(job["job_id"], getattr(call, "object_id", None), job.get("beats_call_id"))


def _calls_key(job_id: str) -> str:
    return f"calls:{job_id}"


def _record_calls(job_id: str, gpu: str | None, beats: str | None = None,
                  token: str | None = None) -> None:
    """Remember which Modal calls are doing this job's work, so a removal can
    cancel them instead of paying for a GPU run whose every write it will
    refuse. In the hand-off Dict, beside the tokens: one small put, and the
    removal is the only reader. Best-effort -- without it the worker still
    stops at its next tombstone check, it just costs a little more GPU."""
    try:
        _handoff()[_calls_key(job_id)] = {"gpu": gpu, "beats": beats, "token": token}
    except Exception as e:  # noqa: BLE001
        print(f"[dispatch] could not record the calls for {job_id}: {e}")


def _cancel_inflight(job_id: str) -> None:
    """Stop this job's running work: drop an unclaimed hand-off and cancel the
    GPU run and the beat proposal. Cancelling a finished call is a no-op, so
    there is nothing to check first. The export stage is not cancelled: it is
    CPU, short, and stops itself at its first tombstone check."""
    try:
        rec = _handoff().pop(_calls_key(job_id), None)
    except Exception as e:  # noqa: BLE001
        print(f"[removal] could not look up the running calls of {job_id}: {e}")
        return
    if not rec:
        return
    if rec.get("token"):
        try:
            _handoff().pop(rec["token"], None)  # a job the container has not picked up yet
        except Exception:  # noqa: BLE001
            pass
    for call_id in (rec.get("gpu"), rec.get("beats")):
        if call_id:
            try:
                modal.FunctionCall.from_id(call_id).cancel()
                print(f"[removal] cancelled {call_id} for {job_id}")
            except Exception as e:  # noqa: BLE001
                print(f"[removal] could not cancel {call_id} for {job_id}: {e}")


@app.middleware("http")
async def _only_through_the_worker(request: Request, call_next):
    # With STEPWISE_ORIGIN_KEY set, this origin answers only the Cloudflare
    # Worker (ratelimit.origin_key_ok). That is what makes the Worker's
    # forwarded client IP trustworthy, and so the per-IP limit real. /health
    # stays open: it is the smoke check and reports no secrets.
    if request.url.path != "/health" and not ratelimit.origin_key_ok(request.headers):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not found."}, status_code=404)
    return await call_next(request)

# clip_id -> unix time we last recorded an access. Purely a write-throttle for
# _touch(); losing it on restart costs one extra small Volume write.
_TOUCHED: dict[str, float] = {}


def _reconstructor():
    # Looked up per-call, not cached at import time: an app redeploy (new
    # code) should be picked up without restarting this service.
    return modal.Cls.from_name(APP_NAME, "Reconstructor")()


def _run_clip_fn():
    """modal_app.run_clip, as it runs on a warm GPU container."""
    return _reconstructor().run


def _spawn_counts(clip_id: str) -> str | None:
    """Start the beat proposal now, beside run_clip rather than inside it.

    It is CPU-only and needs nothing but the uploaded bytes, so spawned here it
    lands ~20 s after upload -- while run_clip is still waiting for a GPU --
    and the processing screen can teach the 8-counts during the wait. run_clip
    gets the call id and only collects it, so the proposal runs once.
    Best-effort: without it the job still runs and run_clip spawns its own.
    """
    try:
        return modal.Function.from_name(APP_NAME, "propose_counts").spawn(clip_id=clip_id).object_id
    except Exception as e:  # noqa: BLE001
        print(f"[dispatch] could not spawn propose_counts for {clip_id}: {e}")
        return None


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
# The line this deliberately does not cross (docs/legal/rights-and-privacy.md):
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


def _usable(entry: dict) -> bool:
    """Does this index entry still point at a lesson we can actually serve?

    Checked against live state, not just the index: the entry must point at a
    job that actually succeeded and has not been taken down. A stale index
    entry therefore degrades to "reconstruct it again" -- which costs $0.08 --
    and can never serve a lesson that is gone.
    """
    clip_id, job_id = entry.get("clip_id"), entry.get("job_id")
    if not clip_id or not job_id:
        return False
    if _volume_read_json(results_volume, f"/{clip_id}.removed.json") is not None:
        return False  # taken down: never resurrect it, and never dedupe onto it
    status = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
    return bool(status and status.get("state") == "succeeded")


def _find_existing(fp: dict) -> dict | None:
    """The canonical lesson for this *content*, if there is a usable one."""
    for entry in retention.read_index(results_volume):
        if fingerprint.same_clip(entry, fp) and _usable(entry):
            return entry
    return None


def _find_by_source(key: str) -> dict | None:
    """The canonical lesson for this *link*, if there is a usable one.

    The cheaper of the two dedupe layers and the reason it exists: a source_key
    match is settled before anything is downloaded, so pasting a link someone
    already turned into a lesson costs one metadata request and no transfer --
    ours or the platform's.
    """
    for entry in retention.read_index(results_volume):
        if entry.get("source_key") == key and _usable(entry):
            return entry
    return None


def _limited(http: Request, charge_as: tuple[str, str] | None = None) -> None:
    """Rate-limit this request: record a dispatch (charge_as=(job_id, clip_id))
    or only check. Over the limit -> 429 in the invite gate's {"error": {...}}
    shape, which both upload doors already render verbatim."""
    ip = ratelimit.client_ip(http.headers, http.client and http.client.host)
    try:
        if charge_as:
            ratelimit.charge(ip, *charge_as)
        else:
            ratelimit.check(ip)
    except ratelimit.Limited as e:
        raise _too_many(e) from None


def _created(http: Request, fp: dict, source: str, clip_id: str, job_id: str,
             deduplicated: bool = False) -> None:
    """analytics `job_created`: every accepted clip, a dedupe hit included
    (flagged), so uploads and GPU runs can both be counted."""
    seconds = fp.get("duration_s")
    analytics.record("job_created", {
        "source": source, "deduplicated": deduplicated,
        "seconds": round(seconds, 1) if seconds is not None else None,
    }, http.headers, http.client and http.client.host, job_id=job_id, clip_id=clip_id)


def _too_many(e: ratelimit.Limited) -> HTTPException:
    return HTTPException(429, headers={"Retry-After": str(e.retry_after)}, detail={"error": {
        "code": e.code, "message": e.message, "retryable": True}})


def _store_and_dispatch(tmp_path: str, clip_id: str, fp: dict, http: Request,
                        source_key: str | None = None, credit: dict | None = None) -> DispatchResponse:
    """The single path from "we have the bytes" to "a job is running".

    Both front doors -- an uploaded file and a pasted link -- end here, so
    there is exactly one place that mints a job, one index shape, and one set
    of artifact names. That is what keeps a takedown complete: a lesson has one
    clip_id no matter which door it came through, so removing it removes it.
    """
    job_id = f"job_{clip_id}"  # resumable: DESIGN.md §7c's copyable link is just this job_id
    # Charged here and nowhere earlier: both dedupe layers have already said
    # "no existing lesson", so this request really will spend a GPU run. And
    # before any byte is stored, so a 429 leaves no half-made lesson behind.
    _limited(http, charge_as=(job_id, clip_id))
    _created(http, fp, "link" if source_key else "file", clip_id, job_id)
    with uploads_volume.batch_upload(force=True) as batch:
        batch.put_file(tmp_path, f"/{clip_id}.mp4")
    # The video goes to R2 here rather than at export time, because these
    # bytes are already on this machine: publishing later would mean reading a
    # 5 MB object back out of a Volume for no reason. The Volume copy stays --
    # run_clip reads its input from there, and moving that is migration step 6
    # (presigned browser uploads), not this one.
    #
    # THIRD INTEGRATION PASS: `deployment` put this call, and the
    # `jobstore.record_dispatch` below, inside `upload_clip` -- which is where
    # they lived when that branch was cut. `link-ingestion` had since moved
    # that whole body here, so that the uploaded-file door and the pasted-link
    # door mint a job exactly once, in one place. Git offered the two as
    # non-overlapping edits to a function one side had deleted; taking that
    # offer would have dropped R2 publishing and the jobstore record from BOTH
    # doors with no conflict and no failing test. Re-derived here instead, and
    # the link door gains both for free -- a linked lesson's video is now
    # range-servable like an uploaded one.
    _publish_video(clip_id, tmp_path)

    # job_id -> clip_id is needed later (retry, result-building) without
    # parsing it back out of the job_id string -- written once, here.
    jobstore.record_dispatch(results_volume, job_id, clip_id, credit)
    entry = dict(fp, clip_id=clip_id, job_id=job_id, created_at=time.time())
    if source_key:
        entry["source_key"] = source_key
    retention.write_index(results_volume, retention.read_index(results_volume) + [entry])

    # The race, handled rather than assumed away. Two people pasting the same
    # link at the same moment both get this far, because the index entry that
    # would have stopped the second one is written after a multi-second
    # download. They agree on clip_id (it is derived from the link), so they
    # can never produce two lessons -- the worst case is one wasted GPU run.
    # This read closes most of that window: if the first job has already
    # written its "queued" document, the second request adopts it instead of
    # spawning again.
    #
    # ponytail: best-effort, and deliberately so. run_clip writes that document
    # from inside a container via a mounted Volume, so there is a real
    # propagation delay in which this read returns nothing for a job that does
    # exist -- the same read-after-write window run_clip's own `uploads.reload()`
    # exists for. Losing the race costs $0.08 and produces no wrong state, so
    # the honest fix (a lease in a store with compare-and-set) is not worth
    # standing up a second storage system for. Revisit if duplicate spawns show
    # up in practice.
    #
    # Deliberately a Volume read and NOT `jobstore.read_status`, even under
    # STEPWISE_JOB_BACKEND=postgres. This asks one question -- "has run_clip
    # started and written its own status document" -- and only the worker
    # writes that document (jobstore.py: the worker still writes the Volume
    # JSON through migration step 3). `record_dispatch` above inserts a
    # `queued` row for THIS request, so reading the row back here would find
    # our own insert and adopt a job nobody ever spawned.
    if _volume_read_json(results_volume, f"/{job_id}.job-status.json") is not None:
        print(f"[dispatch] {job_id} is already running -- adopting it, not spawning again")
        return DispatchResponse(clip_id=clip_id, job_id=job_id, deduplicated=True)

    # A link's clip_id is derived, so it can be taken down by someone else
    # while this request was downloading and storing: the caller checked the
    # tombstone before the download, but the lesson was removed since. This is
    # the job_6037 shape -- a lesson's bytes written after its removal -- and
    # the answer is to take back what was just written and not spend a GPU.
    # An uploaded file's clip_id is a fresh uuid4 nobody else can know yet, so
    # it skips the extra read.
    if source_key and retention.is_removed(results_volume, clip_id):
        retention.delete_clip(uploads_volume, results_volume, clip_id, job_id, "")
        raise HTTPException(410, "This lesson was removed and is not coming back.")

    _dispatch_run(http, clip_id=clip_id, job_id=job_id, beats_call_id=_spawn_counts(clip_id))
    return DispatchResponse(clip_id=clip_id, job_id=job_id)


@app.post("/clips", response_model=DispatchResponse)
async def upload_clip(http: Request, file: UploadFile = File(...)) -> DispatchResponse:
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
            _created(http, fp, "file", existing["clip_id"], existing["job_id"], deduplicated=True)
            return DispatchResponse(clip_id=existing["clip_id"],
                                    job_id=existing["job_id"], deduplicated=True)

        return _store_and_dispatch(tmp_path, uuid.uuid4().hex, fp, http)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# POST /clips/link -- the pasted-TikTok front door.
#
# PRD §5 lists paste-a-link as out of v1, and §8's milestone D parks it in the
# buffer. This ships it early because it is the MVP's actual front door as the
# builder describes it, and the scope note in PRD §5 was updated in the same
# commit rather than left contradicting the code.
#
# **The rights question here is NOT the one rights-and-privacy.md answered.**
# That document analysed people *uploading* clips. Fetching on a stranger's
# behalf from a platform whose terms forbid automated downloading is a
# different act with a different posture, and the conclusions there do not
# transfer. docs/research/link-ingestion.md is the analysis that covers it, and
# its finding is that this is defensible for an invite-only pilot and NOT
# cleared for public launch. The invite gate below is what makes that
# distinction a property of the code rather than of an intention.
#
# Why server-side rather than fetching in the browser: a browser cannot do it
# at all (CORS, and no extractor), and shipping an extractor to the client
# would put the fetch on the visitor's IP under their address while we keep the
# result -- worse for them and no better for us. Doing it here means one place
# to audit, one place to rate-limit, and one place to turn off.
# ---------------------------------------------------------------------------

class LinkRequest(BaseModel):
    url: str


def _refuse(e: ingest.FetchRefused) -> HTTPException:
    """A FetchRefused as HTTP, carrying the job-status error object verbatim.

    422 rather than a per-code status: the structured `error` is the thing the
    client renders, and it is exactly job-status.schema.json's error shape, so
    the failure screen that already handles a failed job handles this too
    without a second vocabulary.
    """
    print(f"[ingest] refused: {e.code} (retryable={e.retryable})")
    return HTTPException(422, detail={"error": e.as_error()})


def _clip_id_for_source(key: str) -> str:
    """One canonical clip_id per source link.

    Derived, not minted, and this is load-bearing: it is what makes two people
    pasting the same link at the same moment land on one lesson even when the
    index lookup that should have caught it loses the race. One lesson means
    one takedown -- a removal reaches everyone who pasted that link, which is
    the whole argument for content-addressing in the first place
    (OPEN-DECISIONS.md D7).

    **The trade, stated rather than buried.** An uploaded clip's link is a
    128-bit uuid4 and is not guessable. A link-ingested clip's is derivable by
    anyone who knows the source URL. For the invite-only pilot that is a small
    exposure on already-public source material, and it cuts the useful way too:
    a dancer who finds their own TikTok reconstructed here can reach the
    removal path without needing anyone to hand them a link. It is not the
    right property for a public launch with no accounts, because today anyone
    holding a lesson link can remove it (D5/D7). Recorded in
    docs/research/link-ingestion.md as a D5 dependency, not smuggled in.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:32]  # uuid4().hex's shape


@app.post("/clips/link", response_model=DispatchResponse)
def ingest_clip_link(request: LinkRequest, http: Request,
                     x_invite_code: str | None = Header(default=None)) -> DispatchResponse:
    if not ingest.invite_code_ok(x_invite_code):
        # Not 404-disguised: someone who was given a code and typed it wrong
        # deserves to know which thing failed, so a missing code and a wrong
        # one are told apart. File upload is still open, and a missing code's
        # message says so rather than leaving them stuck.
        if x_invite_code and x_invite_code.strip():
            raise HTTPException(403, detail={"error": {
                "code": "invite_invalid",
                "message": "That invite code isn't right. Check it and try again.",
                "retryable": False,
            }})
        raise HTTPException(403, detail={"error": {
            "code": "invite_required",
            "message": "Links need an invite code while we try this out. "
                       "Enter yours, or add a video file instead.",
            "retryable": False,
        }})

    try:
        info = ingest.probe(request.url)
    except ingest.FetchRefused as e:
        raise _refuse(e) from None

    key = ingest.source_key(info)
    credit = ingest.credit(info, request.url)

    # Layer 1: the same link, already a lesson. Settled before any download.
    hit = _find_by_source(key)
    if hit:
        print(f"[dedupe] url hit: {key} -> {hit['clip_id']} -- nothing fetched")
        _stamp_credit(hit["job_id"], credit)
        return DispatchResponse(clip_id=hit["clip_id"], job_id=hit["job_id"],
                                deduplicated=True)

    # Before the download, not only at dispatch: an IP already over its limit
    # would otherwise still cost us a fetch per attempt.
    _limited(http)

    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        try:
            ingest.download(request.url, tmp_path)
        except ingest.FetchRefused as e:
            raise _refuse(e) from None

        fp = fingerprint.fingerprint(tmp_path)

        # The metadata gate already refused anything yt-dlp said was over 60 s.
        # This catches the case where it would not say: ffprobe now knows, and
        # dispatching here would hand back a lesson for a silently trimmed
        # dance. Same 0.5 s tolerance the upload screen uses.
        measured = fp.get("duration_s")
        if measured is not None and measured > ingest.MAX_CLIP_SECONDS + 0.5:
            raise _refuse(ingest.FetchRefused(
                "clip_too_long",
                f"That video is {int(measured)} seconds. Up to 60 works -- "
                "trim it to the part you want to learn and upload that.",
                False))

        # Layer 2: the same dance, reached by a different route -- someone
        # uploaded this file yesterday, or pasted a re-upload of it under a
        # different id. Costs the download but still no GPU.
        existing = _find_existing(fp)
        if existing:
            print(f"[dedupe] content hit via link {key}: reusing "
                  f"{existing['clip_id']} -- no GPU run dispatched")
            # Teach the URL layer what the content layer just worked out, so
            # the next paste of this link stops at layer 1 and never downloads.
            # This is also what keeps the two layers converging on ONE clip_id
            # rather than quietly maintaining two ideas of the same lesson.
            _stamp_source_key(existing["clip_id"], key)
            _stamp_credit(existing["job_id"], credit)
            _created(http, fp, "link", existing["clip_id"], existing["job_id"], deduplicated=True)
            return DispatchResponse(clip_id=existing["clip_id"],
                                    job_id=existing["job_id"], deduplicated=True)

        clip_id = _clip_id_for_source(key)
        if _volume_read_json(results_volume, f"/{clip_id}.removed.json") is not None:
            # This link was turned into a lesson and that lesson was taken
            # down. D7 decided a re-upload of removed content is reconstructed
            # afresh rather than blocked, because keeping a blocklist means
            # retaining a derivative of exactly what someone asked us to
            # delete. A fresh random clip_id makes that true here too -- the
            # tombstone keeps its own id and its own 410 forever.
            clip_id = uuid.uuid4().hex
        return _store_and_dispatch(tmp_path, clip_id, fp, http, source_key=key, credit=credit)
    finally:
        os.unlink(tmp_path)


def _stamp_source_key(clip_id: str, key: str) -> None:
    """Record that `key` resolves to an existing lesson. Best-effort."""
    entries = retention.read_index(results_volume)
    changed = False
    for entry in entries:
        if entry.get("clip_id") == clip_id and entry.get("source_key") != key:
            entry["source_key"] = key
            changed = True
    if changed:
        retention.write_index(results_volume, entries)


def _stamp_credit(job_id: str, credit: dict) -> None:
    """Credit a lesson reached by link that has none yet: one made before
    credits were stored, or an uploaded file that turned out to be this link's
    video. Best-effort, like _stamp_source_key. A credit for another post (a
    re-upload that matched by content) is kept; one for this same post is
    refreshed, so a lesson credited before the caption and music fields
    existed gains them when its link is pasted again."""
    path = f"/{job_id}.job-meta.json"
    meta = _volume_read_json(results_volume, path)
    if meta is None:
        return
    old = meta.get("credit")
    if old is None or (ingest.clean_url(old.get("url") or "") == credit["url"] and old != credit):
        retention.write_json(results_volume, path, dict(meta, credit=credit))


@app.get("/jobs/{job_id}/source")
def get_job_source(job_id: str) -> dict:
    """Where a link lesson's video came from: {url, host, creator}, for the
    "Original by @creator on TikTok" line (docs/legal/legal-public-learning.md
    §6(a)2). 404 for an uploaded file, which has no source to credit. Kept out
    of the MotionResult and the job status, both strict contracts; removal
    deletes job-meta, so a removed lesson has no credit either."""
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    if not meta or not meta.get("credit"):
        raise HTTPException(404, "No source link for this lesson.")
    credit = dict(meta["credit"])
    # Credits stored before links were cleaned still carry TikTok's `?_r=1&_t=…`
    # tracking; cleaned on the way out, so old lessons link like new ones.
    if isinstance(credit.get("url"), str):
        credit["url"] = ingest.clean_url(credit["url"])
    return credit


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} -- the polling endpoint W7's ProcessingScreen/lib/jobStatus.ts
# needs. Reads the real job-status.schema.json document run_clip wrote to the
# results Volume, unmodified (no reinterpretation, spec item 5).
# ---------------------------------------------------------------------------

# job_id -> clip_id. The mapping is written once, at dispatch, and never
# changes, so a found one is true forever. Reading an existing file off the
# Volume from this (unmounted) container measured 0.45-1.25 s warm
# (2026-09-24), and /result used to do it twice per request; the jobs row
# answers in ~3 ms on a warm pool.
# A miss is not cached: the meta may simply not exist yet.
_CLIP_OF: dict[str, str] = {}


def _clip_id_from_row(job_id: str) -> Optional[str]:
    if not jobstore.postgres_enabled():
        return None
    try:
        with jobstore.connection() as conn:
            row = conn.execute("SELECT clip_id FROM jobs WHERE job_id = %s", (job_id,)).fetchone()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001 -- the Volume below still answers
        print(f"[jobs] clip_id lookup for {job_id} fell back to the Volume: {e}")
        return None


def _clip_id_for(job_id: str) -> str:
    if job_id in _CLIP_OF:
        return _CLIP_OF[job_id]
    if clip_id := _clip_id_from_row(job_id):
        _CLIP_OF[job_id] = clip_id
        return clip_id
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    if not meta:
        return job_id.removeprefix("job_")
    _CLIP_OF[job_id] = meta["clip_id"]
    return meta["clip_id"]


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


# job_id -> monotonic time its lesson was last confirmed NOT removed. A missing
# tombstone costs ~0.1 s to confirm; a finished job's status is polled on every
# open, so it is confirmed at most this often per replica. A removal on another
# replica shows up here within this window; /result checks every time anyway.
_NOT_REMOVED: dict[str, float] = {}
_REMOVAL_CHECK_S = 30.0


def _refuse_if_removed_cached(job_id: str) -> None:
    seen = _NOT_REMOVED.get(job_id)
    if seen is not None and time.monotonic() - seen < _REMOVAL_CHECK_S:
        return
    _refuse_if_removed(_clip_id_for(job_id))
    _NOT_REMOVED[job_id] = time.monotonic()


def _with_early_counts(doc: dict, job_id: str) -> dict:
    """Fold the beat proposal into a live job's `milestones.counts`.

    propose_counts is spawned at dispatch and writes `{clip_id}.beats.json`
    long before run_clip gets a GPU, so during the queue the worker has
    written nothing that could carry it. Once run_clip has picked the counts
    up itself (its documents then carry them), this costs nothing: the extra
    Volume read only happens while a live job's document lacks them.

    ponytail: a clip with no audio never gets counts, so its polls pay two
    small reads (job-meta, beats) for the whole run. Record "no proposal" in
    the worker's milestones if that ever shows up in latency.
    """
    if doc["state"] not in ("queued", "processing") or (doc.get("milestones") or {}).get("counts"):
        return doc
    counts = milestones.counts_milestone(
        _volume_read_json(results_volume, f"/{_clip_id_for(job_id)}.beats.json"))
    if counts is None:
        return doc
    return dict(doc, milestones=dict(doc.get("milestones") or {}, counts=counts))


# --- Export watchdog --------------------------------------------------------
# run_clip writes EXPORT_STAGE, spawns export_clip_gltf and returns; export
# writes the terminal status. An export container killed without raising (OOM,
# its Modal timeout, a crash) writes nothing, and the job would sit at 0.97
# forever. So once a job has been at this stage longer than export can possibly
# run, the next poll asks Modal about the call and, if it is dead, writes the
# retryable `export_error` export would have written. Measured against the real
# client (2026-09-25): a running or queued call's get(timeout=0) raises the
# builtin TimeoutError; OOM -> restarted until FunctionTimeoutError at the
# function's timeout; os._exit -> restarted, then InternalFailure ("lost track
# of input") after ~60 s in one run but still "running" at 160 s in another --
# hence EXPORT_GIVE_UP_S.
EXPORT_STAGE = "Building the 3D body file"
# modal_app.EXPORT_TIMEOUT_S (600) + room for a CPU container to be scheduled.
EXPORT_STALE_S = 600 + 120
EXPORT_GIVE_UP_S = 3 * EXPORT_STALE_S
_EXPORT_RECHECK_S = 60.0
# (job_id, retry_count) -> {"since": export spawn time, "call": its id or None,
# "next": when to look again}. Per replica, so a running job's poll costs a
# dict lookup: the hand-off Dict is read about once a minute until it names the
# call, and Modal is only asked once the export is overdue.
_EXPORT_WATCH: dict[tuple[str, int], dict] = {}


def _export_call_dead(call_id: str) -> bool:
    try:
        modal.FunctionCall.from_id(call_id).get(timeout=0)
    except (OSError, modal.exception.ConnectionError):
        return False  # builtin TimeoutError: still queued/running; or we could not ask
    except Exception:  # noqa: BLE001 -- it raised, timed out or was lost: it will write nothing more
        return True
    return False  # it returned: its own status write is already on the Volume


def _fail_dead_export(doc: dict, job_id: str) -> dict:
    if doc["state"] != "processing" or doc["stage_message"] != EXPORT_STAGE:
        return doc
    now = time.time()
    w = _EXPORT_WATCH.setdefault((job_id, doc["retry_count"]), {"since": now, "call": None, "next": now})
    if now < w["next"]:
        return doc
    if w["call"] is None:
        try:
            rec = _handoff().get(_calls_key(job_id)) or {}
        except Exception as e:  # noqa: BLE001 -- keep timing it from when this replica first saw it
            print(f"[watchdog] could not read the calls of {job_id}: {e}")
            rec = {}
        if rec.get("export") and rec.get("retry_count") == doc["retry_count"]:
            w["call"], w["since"] = rec["export"], rec.get("export_at") or w["since"]
    due = w["since"] + EXPORT_STALE_S
    if now < due:
        w["next"] = due if w["call"] else now + _EXPORT_RECHECK_S
        return doc
    w["next"] = now + _EXPORT_RECHECK_S
    # No recorded call (a failed put, or a GPU that died between the status
    # write and the spawn): time alone, which is already past export's timeout.
    # A call Modal still calls running past EXPORT_GIVE_UP_S is given up on too:
    # a crash-looping container is restarted, and reported running, for longer.
    if w["call"] and now < w["since"] + EXPORT_GIVE_UP_S and not _export_call_dead(w["call"]):
        return doc
    # A removed lesson stays 410; it never turns into a retryable failure.
    _refuse_if_removed(_clip_id_for(job_id))
    if w["call"]:
        try:  # a no-op on a dead call; on a given-up one it stops a late write racing ours
            modal.FunctionCall.from_id(w["call"]).cancel()
        except Exception as e:  # noqa: BLE001
            print(f"[watchdog] could not cancel {w['call']} for {job_id}: {e}")
    # Re-read last: whatever landed meanwhile (a `succeeded`, a retry) wins.
    fresh = jobstore.read_status(results_volume, job_id, _clip_id_for)
    if fresh is None or (fresh["state"], fresh["stage_message"], fresh["retry_count"]) != \
            (doc["state"], doc["stage_message"], doc["retry_count"]):
        return fresh or doc
    failed = dict(jobstore.queued_doc(job_id), state="failed", retry_count=doc["retry_count"], error={
        "code": "export_error",
        "message": "Building the 3D body file stopped before it finished. Trying again usually works.",
        "retryable": True})
    # The Volume document, as export itself would have written it; postgres
    # mode mirrors it into the row on the next read, as it would export's.
    retention.write_json(results_volume, f"/{job_id}.job-status.json", failed)
    observability.message("export died without a status", "web", level="error",
                          job_id=job_id, retry_count=doc["retry_count"], call=w["call"] or "unknown")
    _EXPORT_WATCH.pop((job_id, doc["retry_count"]), None)
    return failed


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    doc = jobstore.read_status(results_volume, job_id, _clip_id_for)
    if doc is None:
        # Removal deletes the job-status document, so a MISSING one is the
        # usual removed lesson (terminal ones are caught below) -- which is why
        # the tombstone is checked here and not at the top. This endpoint is polled every second
        # or so by the processing screen, and the common path (a job that is
        # genuinely running) must stay at exactly one Volume read, the way it
        # was before removal existed.
        #
        # Without this check a removed lesson would report "queued" forever:
        # the most misleading possible answer, since the thing it is waiting
        # for is never coming.
        _refuse_if_removed(_clip_id_for(job_id))
        # A job that was just spawned and hasn't written its first "queued"
        # doc yet is a real, valid state -- but _store_and_dispatch writes
        # job-meta BEFORE the spawn, so no meta either means this job_id never
        # existed. Without the 404 a mistyped lesson link waits on "queued"
        # forever.
        if _volume_read_json(results_volume, f"/{job_id}.job-meta.json") is None:
            raise HTTPException(404, "No lesson at this link.")
        doc = jobstore.queued_doc(job_id)
    elif doc["state"] in ("succeeded", "failed"):
        # A lesson removed WHILE its job ran: the worker writes its final status
        # (and npz) after delete_clip, so a status document can exist for a
        # removed lesson (job_6037..., 2026-09-25). Terminal states only -- a
        # running job's polls stay at one Volume read -- and at most one
        # tombstone read per job per _REMOVAL_CHECK_S per replica.
        _refuse_if_removed_cached(job_id)
    doc = _fail_dead_export(doc, job_id)
    doc = _with_early_counts(doc, job_id)
    result = validate_job_status(doc)
    if not result.valid:
        # Fail loudly, not silently -- serving a contract-invalid document is
        # worse than a 500 (DESIGN.md §7h's honesty rule applies to plumbing
        # too, not just copy).
        raise HTTPException(500, f"job-status document failed contract validation: {result.errors}")
    if doc["state"] == "succeeded":
        _prime_result(job_id)
    if doc["state"] in ("succeeded", "failed"):
        clip_id = _clip_id_for(job_id)
        analytics.record_finished(doc, clip_id, lambda: len((_volume_read_json(
            results_volume, f"/{clip_id}.export-manifest.json") or {}).get("glb_paths") or {}))
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

# Two retries, then stop: a clip that crashed three times will crash a fourth,
# and every attempt is a paid GPU run.
MAX_RETRIES = 2


@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, http: Request) -> dict:
    doc = jobstore.read_status(results_volume, job_id, _clip_id_for)
    if doc is None:
        raise HTTPException(404, "Unknown job_id.")
    # Never re-run the GPU on a lesson someone took down.
    _refuse_if_removed(_clip_id_for(job_id))
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

    if doc["retry_count"] >= MAX_RETRIES:
        raise HTTPException(409, detail={"error": {
            "code": "retries_exhausted",
            "message": "This clip failed again after two retries, so we stopped trying. "
                       "Uploading a different recording of the dance usually works.",
            "retryable": False}})

    retry_count = doc["retry_count"] + 1
    _limited(http, charge_as=(job_id, meta["clip_id"]))  # a retry is a GPU run like any other
    jobstore.record_retry(results_volume, job_id, meta["clip_id"], retry_count)
    call = _run_clip_fn().spawn(clip_id=meta["clip_id"], job_id=job_id, retry_count=retry_count)
    _record_calls(job_id, getattr(call, "object_id", None))
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

# (clip_id, job_id, sha256 of the stored bytes) already validated in this
# replica. An export writes a new object, so a new sha, so it is validated
# again; nothing else can change what a key names.
_VALID_STORED: set[tuple[str, str, str]] = set()
_PRIMED: set[str] = set()
# One validation at a time. It is CPU-bound under the GIL, so parallel runs
# only slow each other down: four opens of one lesson on a cold container took
# 78-82 s EACH (2026-09-25 logs) where one alone took ~30 s. Serialised, the
# second request finds the first one's verdict in _VALID_STORED.
# ponytail: global, not per-key; per-key if two different cold lessons ever
# queue behind each other in practice.
_VALIDATING = threading.Lock()
# (job_id, clip_id) -> (the R2 key its validated MotionResult lives at, when
# that was read). The key is versioned, so a re-export moves it; the verdict is
# kept for _R2_VALIDATED_S, well inside the grace export_clip_gltf gives the old
# version before deleting it (modal_app.OLD_VERSION_GRACE_S), so no replica
# redirects to an object that is gone. Removal is checked before this is ever
# consulted.
_R2_VALIDATED: dict[tuple[str, str], tuple[str, float]] = {}
_R2_VALIDATED_S = 60.0


def _validated_r2_url(job_id: str, clip_id: str) -> Optional[str]:
    """A URL for the stored MotionResult straight from R2, when the exporter
    validated it for THIS job_id (modal_app.export_clip_gltf writes
    `validated: <job_id>` metadata in the same PUT as the bytes), else None.

    This is the learner's first-open path: no replica has to download,
    decompress and re-validate the document (20-30 s on a cold web container,
    the "second wait" after Start learning), and the browser gets the ~1 MB
    gzip from R2 with its own Content-Encoding instead of through two proxies.
    Anything unmarked -- older lessons, a deduplicated job whose document
    carries another job_id, R2 down -- takes `_stored_result` as before.

    The browser is sent to the immutable, versioned copy the latest object's
    `version` metadata names, so a re-exported lesson is a new URL rather than
    a year-cached old one. A lesson exported before versioning has no
    `version` and is served from the latest key, as before.
    """
    if not storage.enabled():
        return None
    hit = _R2_VALIDATED.get((job_id, clip_id))
    if hit and time.monotonic() - hit[1] < _R2_VALIDATED_S:
        return storage.url_for(hit[0])  # presigning is local: no round trip
    try:
        head = storage.client().head_object(Bucket=storage.bucket(),
                                            Key=storage.motion_result_key(clip_id))
        meta = head.get("Metadata") or {}
        if meta.get("validated") != job_id:
            return None
        key = storage.motion_result_key(clip_id, meta.get("version"))
        _R2_VALIDATED[(job_id, clip_id)] = (key, time.monotonic())
        return storage.url_for(key)
    except Exception:  # noqa: BLE001 -- missing or unreachable: the byte path decides
        return None


def _stored_result(job_id: str, clip_id: str) -> Optional[bytes]:
    """The stored MotionResult as gzip bytes, contract-validated once, or None.

    Validation stays (DESIGN.md §7h: never serve a contract-invalid document)
    but runs once per stored object per replica, not per open -- it is 2.9 s
    on a laptop and 20-30 s on a cold Modal web container. Only for documents
    `_validated_r2_url` cannot vouch for.
    """
    stored = _r2_read(storage.motion_result_key(clip_id)) \
        or _volume_read_bytes(results_volume, f"/{clip_id}.motion-result.json.gz")
    if stored is None:
        return None
    key = (clip_id, job_id, hashlib.sha256(stored).hexdigest())
    if key in _VALID_STORED:
        return stored
    with _VALIDATING:
        if key in _VALID_STORED:
            return stored
        return _validate_stored(stored, job_id, key)


def _validate_stored(stored: bytes, job_id: str, key: tuple[str, str, str]) -> bytes:
    doc = json.loads(gzip.decompress(stored))
    stamped = doc.get("job_id") != job_id
    if stamped:
        # Written by whichever job first reconstructed this clip; a deduplicated
        # upload is normally handed that same job_id, so this is rare. Stamping
        # keeps "the id of the job that produced this result" honest.
        doc["job_id"] = job_id
    result = validate_motion_result(doc)
    if not result.valid:
        raise HTTPException(500, f"Stored MotionResult failed contract validation: {result.errors}")
    if stamped:
        return gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), 6)
    _VALID_STORED.add(key)
    return stored


def _prime_result(job_id: str) -> None:
    """Validate a just-succeeded lesson in the background, so the learner's
    first open (seconds later, from the processing screen) is a cache hit."""
    if job_id in _PRIMED:
        return
    _PRIMED.add(job_id)

    def run():
        try:
            clip_id = _clip_id_for(job_id)
            # Already validated at export: nothing to do, and a 20-30 s
            # validation here would only compete for the GIL with the open.
            if _validated_r2_url(job_id, clip_id) is None:
                _stored_result(job_id, clip_id)
        except Exception as e:  # noqa: BLE001 -- the real request reports it
            print(f"[result] could not prime {job_id}: {e}")

    threading.Thread(target=run, daemon=True).start()


# Jobs this replica has seen succeed. Succeeded is terminal (retry only takes a
# failed job), so the one thing that can change afterwards is a removal -- and
# /result checks the tombstone on every request before trusting this.
_SUCCEEDED: set[str] = set()


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str, tasks: BackgroundTasks = None):
    clip_id = _clip_id_for(job_id)
    # First and on every request, cache or no cache: this is the endpoint that
    # hands over the actual reconstruction, so it does not get to assume some
    # earlier call already refused, and no in-process cache below may outlive
    # a removal made on another replica. One Volume read.
    _refuse_if_removed(clip_id)
    if job_id not in _SUCCEEDED:
        status = get_job_status(job_id)
        if status["state"] != "succeeded":
            raise HTTPException(409, f"Job is '{status['state']}', not 'succeeded'.")
        _SUCCEEDED.add(job_id)
    # The last-access marker is a Volume write: after the response, not before
    # it. Called directly (tests, no request) it just runs inline.
    def touch():
        if tasks is None:
            _touch(clip_id)
        else:
            tasks.add_task(_touch, clip_id)

    url = _validated_r2_url(job_id, clip_id)
    if url is not None:
        touch()
        # 302 like /assets: not cacheable, the URL on the other end expires.
        return RedirectResponse(url, status_code=302)

    stored = _stored_result(job_id, clip_id)
    if stored is not None:
        touch()
        # Already gzipped and already validated: handed over byte-for-byte.
        # Re-parsing, re-validating and re-encoding an 11.7 MB document on
        # every open took 13 s before the first byte on Modal (solo-02).
        return Response(stored, media_type="application/json",
                        headers={"Content-Encoding": "gzip"})
    try:
        doc = motion_result.build_motion_result(
            job_id, clip_id,
            _volume_read_bytes(results_volume, f"/{clip_id}.npz"),
            _volume_read_json(results_volume, f"/{clip_id}.export-manifest.json"),
            _volume_read_json(results_volume, f"/{clip_id}.performance.json"),
            _volume_read_json(results_volume, f"/{clip_id}.beats.json"),
        )
    except motion_result.MotionResultUnavailable as e:
        raise HTTPException(e.status, e.detail) from e

    result = validate_motion_result(doc)
    if not result.valid:
        raise HTTPException(500, f"Assembled MotionResult failed contract validation: {result.errors}")

    touch()
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
        # Runs after the response, so a removal can land between /result's
        # tombstone check and this write; without the re-check the marker is
        # a removed lesson's leftover. Once a day per lesson per replica.
        if retention.is_removed(results_volume, clip_id):
            return
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

@app.get("/jobs/{job_id}/video")
def get_job_video(job_id: str) -> Response:
    """The clip itself, addressed by job_id instead of asset id.

    W7's ProcessingScreen plays the learner's own file from a local blob URL
    and falls back to this while the job runs (DESIGN.md §7c: the video is
    useful immediately, there is no dead time). A pasted link has no local
    blob -- the visitor never held the file -- so for the link path this
    fallback is not a fallback, it is the only source, and without it the
    "your clip plays the whole time it is working" promise is not kept for
    half the front door.

    A thin alias rather than a second implementation: it resolves job_id to
    clip_id and hands off to `get_asset`, so the tombstone check and the 410
    behaviour are the same code and cannot drift apart.
    """
    return get_asset(f"video:{_clip_id_for(job_id)}")


@app.get("/jobs/{job_id}/detections")
def get_job_detections(job_id: str) -> Response:
    """The detector's 2D pass (milestones.build_detections), for the skeleton
    the processing screen draws over the clip while the 3D is built. 404 until
    run_clip's detection pass has written it; the screen only asks once
    `milestones.dancers` says it exists. Same tombstone rule as everything
    else derived from the person's video."""
    clip_id = _clip_id_for(job_id)
    _refuse_if_removed(clip_id)
    body = _volume_read_bytes(results_volume, f"/{clip_id}.detections.json")
    if body is None:
        raise HTTPException(404, "No detections for this job yet.")
    return Response(content=body, media_type="application/json")


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
# docs/legal/rights-and-privacy.md section 1 and 6.1: the largest real
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
    # Plain boxes, none of them a legal category: the dancer (no copyright
    # claim, the person most likely to ask -- rights-and-privacy.md 6.1),
    # someone under 18 in the clip (legal-public-learning.md §5: asked, never
    # estimated), the rights holder, and everyone else. Required, because the
    # owner alert is only useful if it says which kind of request this was.
    relationship: Literal["i_am_in_it", "under_18", "i_own_the_rights", "other"]
    # Optional free text. Kept on the tombstone only (so whoever restores or
    # disputes a removal can read why); never sent to Sentry or the events
    # table, where it could carry a name or a handle.
    reason: str = Field("", max_length=500)


class RemovalResponse(BaseModel):
    clip_id: str
    removed: list[str]
    already_absent: list[str]


@app.post("/jobs/{job_id}/removal", response_model=RemovalResponse)
def remove_lesson_by_job(job_id: str, request: RemovalRequest, http: Request) -> RemovalResponse:
    """The same takedown, addressed the way the web knows a lesson: its job_id
    (the /lesson/{job_id} link). Resolved through job-meta like every other
    /jobs route, so a deduplicated upload removes the one canonical lesson."""
    return remove_lesson(_clip_id_for(job_id), request, http)


@app.post("/lessons/{clip_id}/removal", response_model=RemovalResponse)
def remove_lesson(clip_id: str, request: RemovalRequest, http: Request) -> RemovalResponse:
    """Delete every stored byte of one lesson, now.

    Goes away: the source video, every dancer's GLB, the materialised
    MotionResult, the npz if one still exists, the export manifest, the
    performance record, the last-access marker, the job status and job meta,
    and the content fingerprint. What is left is a tombstone holding a
    timestamp, the relationship category and whatever reason the requester
    chose to type (500 chars max) -- nothing derived from the video.

    Because uploads are deduplicated, there is exactly one canonical copy of a
    given clip, so this removes it for everyone who uploaded it rather than for
    whichever copy happened to be found.
    """
    job_id = f"job_{clip_id}"
    if retention.is_removed(results_volume, clip_id):
        # Already removed: no second charge and no second alert, but the sweep
        # runs again. It is idempotent, and it is how anything a late writer
        # put back after the first removal goes (job_6037...).
        outcome = retention.delete_clip(uploads_volume, results_volume, clip_id, job_id, "")
        return RemovalResponse(clip_id=clip_id, removed=outcome["deleted"],
                               already_absent=outcome["already_absent"])

    if _volume_read_json(results_volume, f"/{job_id}.job-meta.json") is None:
        # Older lessons (and the eval clips) used other job_id shapes; find it
        # rather than leaving a live job-status record pointing at deleted bytes.
        for entry in retention.read_index(results_volume):
            if entry.get("clip_id") == clip_id and entry.get("job_id"):
                job_id = entry["job_id"]
                break

    # Charged only for a removal that is about to happen: an already-removed
    # lesson above costs nothing, so a repeat click is never what locks you out.
    ip = ratelimit.client_ip(http.headers, http.client and http.client.host)
    try:
        ratelimit.charge_removal(ip, clip_id, request.relationship)
    except ratelimit.Limited as e:
        raise _too_many(e) from None

    # Tombstone first: every writer stops at its next check from this instant.
    # Then stop the work that is still running, then delete what exists.
    # (delete_clip would write the tombstone itself; doing it here puts the
    # cancel between the two.)
    retention.write_tombstone(results_volume, clip_id, request.reason.strip(), request.relationship)
    _cancel_inflight(job_id)
    outcome = retention.delete_clip(uploads_volume, results_volume, clip_id, job_id,
                                    request.reason.strip(), request.relationship)
    _TOUCHED.pop(clip_id, None)
    # Belt and braces: /result checks the tombstone before these anyway.
    _SUCCEEDED.discard(job_id)
    _R2_VALIDATED.pop((job_id, clip_id), None)
    _NOT_REMOVED.pop(job_id, None)
    print(f"[removal] {clip_id}: deleted {len(outcome['deleted'])} artifacts ({request.relationship})")
    # The owner's alert. Ids and the category only -- the free-text reason is
    # on the tombstone and deliberately not here.
    observability.message("lesson removed", "web", level="warning",
                          relationship=request.relationship, clip_id=clip_id)
    return RemovalResponse(clip_id=clip_id, removed=outcome["deleted"],
                           already_absent=outcome["already_absent"])


# ---------------------------------------------------------------------------
# Analytics (analytics.py). POST /events is the browser's beacon: a batch of
# allowlisted {name, props}, no identifier. It always answers 200 -- a bad or
# over-cap event is dropped, and no database means everything is dropped.
# Dashboards are PostHog (analytics.forward); there is no read endpoint here.
# ---------------------------------------------------------------------------

@app.post("/events")
async def post_events(http: Request, tasks: BackgroundTasks) -> dict:
    body = await http.body()
    return {"accepted": analytics.ingest(body, http.headers, http.client and http.client.host,
                                         defer=tasks.add_task)}


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
