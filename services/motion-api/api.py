"""W4: the HTTP layer between an uploaded clip and a real Modal GPU job.

Deliberately thin. This process never touches CUDA/torch/pymomentum -- it
only talks to Modal's control plane (spawn a Function, read/list a Volume)
and to disk for the upload's temp file, so it can run anywhere (a laptop, a
small always-on box) independent of the GPU image. The real pipeline lives in
modal_app.py + tools/process_clip.py; this file wires it to HTTP.

Object storage decision (see docs/PRD.md, docs/OPEN-DECISIONS.md E1 note on
GPU host): **Modal Volumes, not S3.** modal_app.py already uses three Volumes
(weights/eval-clips/results) as the only storage layer for everything the
pipeline reads and writes -- run_clip reads its input clip from a Volume path
and writes its job-status/npz/GLB output to one. Standing up S3/MinIO here
would mean two storage systems for one job (uploads in S3, everything
downstream in Modal Volumes) with a copy step between them for no benefit --
Volumes are already reachable from any process holding a Modal token (this
file proves it: no Modal container needed to read/write one), version data
with `.commit()`, and require zero new infrastructure or credentials beyond
what modal_app.py already needs. Cost: Volume reads go through Modal's client
library, not raw HTTP GET, so `/assets/{asset_id}` proxies bytes through this
service rather than redirecting to a public URL -- acceptable at this scale,
and swappable for real S3 + presigned URLs later without changing the
contract (asset_id stays opaque either way, see AnimationRef's schema
comment: never a signed/expiring URL AS the id itself).

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

**Link ingestion** (`POST /clips` with a `url` field instead of a file) adds a
second binary, `yt-dlp`, and one deliberate scope change -- docs/PRD.md §5
listed paste-a-link as out of v1 and has been *updated*, not quietly
contradicted. Read ingest.py's docstring and docs/research/link-ingestion.md
before widening it: the fetch runs behind an invite-code allowlist that fails
closed, because both platforms' terms prohibit automated downloading, and doing
it on behalf of strangers is a different posture from the private eval fetching
in evaluation/fetch.py.

The fetch runs in THIS process, not in a Modal container, deliberately.
evaluation/README.md's existing finding is that platform rate-limiting and bot
checks are far worse from datacenter IPs, and this file was already built to
run on a laptop or a small always-on box. It is dispatched as a FastAPI
background task so the multi-second fetch never blocks the HTTP response.
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
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import fingerprint
import ingest
import motion_result
import retention

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages" / "motion-contract" / "python"))
from motion_contract import validate_job_status, validate_motion_result  # noqa: E402

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
#
# **Link ingestion adds two cheaper gates in front of the fingerprint, and all
# three converge on one `clip_id`.** They are ordered by what they cost:
#
#   1. `source_url_alias` -- the *syntactic* key of the pasted link, matched
#      with zero network access. This is the common case the builder described:
#      the same TikTok share link pasted by several learners. Costs nothing at
#      all, not even a probe.
#   2. `source_url_key` -- the *canonical* key, after one metadata probe that
#      fetches no media. This is what makes `/t/ZP83Enx4b/` and
#      `tiktok.com/@user/video/7672198121417444628` land on the same lesson.
#   3. The perceptual fingerprint, after the download. The same dance arriving
#      as a re-upload, or from a mirror of the same video on the other platform.
#
# The convergence is not three parallel mechanisms: all three match against the
# SAME index entry, which already carries the fingerprint, so a removal that
# drops that one entry (retention.remove_fingerprint) closes all three doors at
# once. There is no second table for URLs that a takedown could miss. That is
# the property the removal path depends on -- a deleted lesson must be gone for
# everyone regardless of how they arrived at it.
# ---------------------------------------------------------------------------

class DispatchResponse(BaseModel):
    clip_id: str
    job_id: str
    # True when this upload matched an existing reconstruction and no GPU work
    # was started. The client needs no special handling -- the job it is handed
    # is already "succeeded", so the normal poll goes straight to the lesson.
    deduplicated: bool = False


def _find_existing(fp: dict | None = None, url_key: str | None = None) -> dict | None:
    """The canonical lesson for this content, if there is a usable one.

    Matches on the URL key, the URL alias, or the perceptual fingerprint --
    whichever the caller has at this point in the pipeline. One scan, one
    liveness rule, one returned entry, so every gate produces the same
    canonical `clip_id`.

    'Usable' is checked against live state, not just the index: the entry must
    point at a job that actually succeeded and has not been taken down. A stale
    index entry therefore degrades to "reconstruct it again" -- which costs
    $0.08 -- and can never serve a lesson that is gone.
    """
    for entry in retention.read_index(results_volume):
        by_url = bool(url_key) and url_key in (entry.get("source_url_key"),
                                               entry.get("source_url_alias"))
        if not by_url and not (fp is not None and fingerprint.same_clip(entry, fp)):
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


def _write_status(job_id: str, state: str, stage_message: str, progress, error=None) -> None:
    """Write one job-status document, validated against the contract first.

    The GPU worker writes its own status documents through a mounted Volume
    (modal_app.run_clip); this is the same document written from outside a
    container, for the stages that happen before a GPU is involved at all.
    Validating here rather than only on read means a bad document never
    reaches the Volume, so `get_job_status` cannot be forced into a 500.
    """
    doc = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "state": state,
        "stage_message": stage_message,
        "progress": progress,
        "error": error,
        "retry_count": 0,
    }
    result = validate_job_status(doc)
    if not result.valid:  # pragma: no cover -- a bug here, not a runtime condition
        raise RuntimeError(f"refusing to write an invalid job-status: {result.errors}")
    retention.write_json(results_volume, f"/{job_id}.job-status.json", doc)


def _store_and_dispatch(tmp_path: str, fp: dict, clip_id: str, job_id: str,
                        index_extra: dict | None = None) -> None:
    """Put the clip where the GPU can read it, record it, and start the run."""
    with uploads_volume.batch_upload() as batch:
        batch.put_file(tmp_path, f"/{clip_id}.mp4")
    # job_id -> clip_id is needed later (retry, result-building) without
    # parsing it back out of the job_id string -- write it once, here.
    retention.write_json(results_volume, f"/{job_id}.job-meta.json",
                         dict(index_extra or {}, clip_id=clip_id))
    retention.write_index(results_volume, retention.read_index(results_volume) + [
        dict(fp, clip_id=clip_id, job_id=job_id, created_at=time.time(),
             **(index_extra or {})),
    ])
    _run_clip_fn().spawn(clip_id=clip_id, job_id=job_id)


def _alias_to(job_id: str, existing: dict, gate: str) -> None:
    """Point an already-issued job_id at the lesson that already exists.

    Gates 2 and 3 fire *after* the client has been handed a job_id, so unlike
    gate 1 they cannot simply return the canonical ids. This writes the
    redirection into job-meta, which `get_job_status` and `_clip_id_for`
    already read.

    The alias job-meta is deliberately NOT deleted by a takedown
    (retention.clip_artifact_paths). It holds two opaque ids and nothing
    derived from any person, and it is the only thing that lets a stale link
    answer 410 Gone after the lesson is removed. Delete it and `_clip_id_for`
    falls back to parsing the job_id, finds no tombstone, and reports "queued"
    forever -- the single most misleading answer available.
    """
    retention.write_json(results_volume, f"/{job_id}.job-meta.json",
                         {"clip_id": existing["clip_id"],
                          "canonical_job_id": existing["job_id"]})
    retention.remove_file_if_present(results_volume, f"/{job_id}.job-status.json")
    print(f"[dedupe] gate {gate}: {job_id} -> {existing['clip_id']} "
          f"(job {existing['job_id']}) -- no GPU run dispatched")


@app.post("/clips", response_model=DispatchResponse)
async def create_clip(
    background: BackgroundTasks,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    x_invite_code: str | None = Header(None),
) -> DispatchResponse:
    """One front door, two ways in: a file, or a link to fetch.

    The link path returns before the fetch finishes -- a yt-dlp probe plus
    download is multi-second and must not be held open across an HTTP request.
    The job it hands back is real and pollable from the first moment; the fetch
    reports into it the same way the GPU stages do.
    """
    if url:
        return _accept_link(background, url, x_invite_code)
    if file is None:
        raise HTTPException(400, "Send a video file, or a link to one.")
    return await upload_clip(file)


async def upload_clip(file: UploadFile) -> DispatchResponse:
    """The original file path, unchanged. Kept under its own name so the
    existing dedupe tests (test_retention.py) call it directly."""
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
        existing = _find_existing(fp=fp)
        if existing:
            print(f"[dedupe] gate 3 (fingerprint): reusing {existing['clip_id']} "
                  f"(job {existing['job_id']}) -- no GPU run dispatched")
            return DispatchResponse(clip_id=existing["clip_id"],
                                    job_id=existing["job_id"], deduplicated=True)

        clip_id = uuid.uuid4().hex
        job_id = f"job_{clip_id}"  # resumable: DESIGN.md §7c's copyable link is just this job_id
        _store_and_dispatch(tmp_path, fp, clip_id, job_id)
    finally:
        os.unlink(tmp_path)

    return DispatchResponse(clip_id=clip_id, job_id=job_id)


# ---------------------------------------------------------------------------
# The link path. See ingest.py for URL normalisation, the failure vocabulary
# and the invite gate; this is only the wiring.
# ---------------------------------------------------------------------------

def _accept_link(background: BackgroundTasks, url: str,
                 invite_code: str | None) -> DispatchResponse:
    link = ingest.normalize(url)
    if link is None:
        # Knowable with no network and no job: there is nothing to observe, so
        # there is nothing to report into a job-status document and nothing a
        # retry could change. Answered immediately instead.
        raise HTTPException(400, "That link is not a TikTok or YouTube video. "
                                 "Paste a link to one, or upload the file.")

    if not ingest.invite_codes():
        # Fails CLOSED. An unconfigured deploy is not a public downloader.
        raise HTTPException(503, "Pasting a link is not switched on here. "
                                 "Upload the file instead.")
    if not ingest.invite_ok(invite_code):
        raise HTTPException(403, "Pasting a link is open to invited testers "
                                 "while this is being tried out. Upload the file instead.")
    if not ingest.ytdlp_available():
        raise HTTPException(503, "Pasting a link is not switched on here. "
                                 "Upload the file instead.")

    # Gate 1 -- free. No probe, no network, no job minted.
    existing = _find_existing(url_key=link.key)
    if existing:
        print(f"[dedupe] gate 1 (pasted url {link.key}): reusing {existing['clip_id']} "
              f"(job {existing['job_id']}) -- nothing fetched")
        return DispatchResponse(clip_id=existing["clip_id"],
                                job_id=existing["job_id"], deduplicated=True)

    # Both ids are minted now, so `job_{clip_id}` holds for link jobs too and
    # remove_lesson's job_id reconstruction keeps working unchanged.
    clip_id = uuid.uuid4().hex
    job_id = f"job_{clip_id}"
    # Written before the fetch starts, not after it succeeds: a fetch that
    # fails retryably needs the link to retry, and at that point there is no
    # index entry to recover it from.
    retention.write_json(results_volume, f"/{job_id}.job-meta.json",
                         {"clip_id": clip_id, "source_url": link.fetch_url})
    _write_status(job_id, "processing", "Fetching the video", 0.02)
    background.add_task(_ingest_link, link, clip_id, job_id)
    return DispatchResponse(clip_id=clip_id, job_id=job_id)


def _ingest_link(link: ingest.Link, clip_id: str, job_id: str) -> None:
    """Probe, refuse or fetch, fingerprint, dispatch. Runs after the response.

    ponytail: a FastAPI background task, so a restart mid-fetch leaves the job
    at "processing" with nothing working on it. Acceptable while this is
    invite-only and single-replica; the upgrade path is the same durable queue
    a second replica would need anyway. It is not silent -- the job is visibly
    stuck rather than wrongly reported as failed or succeeded.
    """
    tmp_path = None
    try:
        probed = ingest.probe(link)
        # Refused BEFORE any media is fetched: the probe is metadata only.
        ingest.check_duration(probed)

        # Gate 2 -- one probe spent, still no media. This is where a share
        # link and the full canonical URL for the same video converge.
        canon = ingest.canonical_key(link.platform, probed) or link.key
        if canon != link.key:
            existing = _find_existing(url_key=canon)
            if existing:
                _alias_to(job_id, existing, f"2 (canonical url {canon})")
                return

        _write_status(job_id, "processing", "Fetching the video", 0.05)
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        os.unlink(tmp_path)  # yt-dlp wants to create it itself
        ingest.download(link, tmp_path)

        fp = fingerprint.fingerprint(tmp_path)
        # Gate 3 -- the same dance by a different route: a re-upload of the
        # file, or the same video mirrored onto the other platform.
        existing = _find_existing(fp=fp)
        if existing:
            _alias_to(job_id, existing, "3 (fingerprint)")
            return

        # A takedown can land while the fetch is running -- the fetch takes
        # seconds and the removal endpoint is always open. Without this check
        # the removal writes a tombstone, the fetch then finishes and stores
        # the clip anyway, and a GPU burns on a lesson somebody has already
        # asked to have deleted. Observed 2026-09-20 before this guard existed.
        # Checked here rather than in `remove_lesson` because this is the side
        # that knows when the clip actually lands.
        #
        # `.reload()` is required, not defensive: a Volume handle serves reads
        # from the commit it last saw, so without it this read returns the
        # state from before the takedown and the guard silently never fires.
        # Observed 2026-09-20 -- the tombstone was on the Volume and this read
        # still came back empty. modal_app.py hits the same hazard on the
        # uploads Volume and documents it there.
        results_volume.reload()
        if _volume_read_json(results_volume, f"/{clip_id}.removed.json") is not None:
            print(f"[ingest] {clip_id} was removed while it was being fetched -- "
                  "not stored, no GPU dispatched")
            retention.remove_file_if_present(results_volume, f"/{job_id}.job-status.json")
            return

        _write_status(job_id, "processing", "Getting the video ready", 0.1)
        _store_and_dispatch(tmp_path, fp, clip_id, job_id, index_extra={
            "source_url": link.fetch_url,
            "source_url_key": canon,
            # The pasted form, kept only when it differs, so gate 1 hits for
            # the next person who pastes the same share link.
            "source_url_alias": None if canon == link.key else link.key,
        })
        print(f"[ingest] {canon} -> {clip_id} ({os.path.getsize(tmp_path) / 1e6:.1f} MB)")
    except ingest.FetchError as e:
        print(f"[ingest] {link.key} failed: {e.code}")
        _write_status(job_id, "failed", "", None, error=e.as_job_error())
    except Exception as e:  # noqa: BLE001
        # Never leave a job at "processing" because of a bug in this function.
        # §7h: the message says the fetch did not go through, not why -- the
        # exception is for the log, not for the learner.
        print(f"[ingest] {link.key} raised: {e!r}")
        code, message, retryable = ingest.classify("")  # nothing observed -> no reason claimed
        _write_status(job_id, "failed", "", None,
                      error={"code": code, "message": message, "retryable": retryable})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} -- the polling endpoint W7's ProcessingScreen/lib/jobStatus.ts
# needs. Reads the real job-status.schema.json document run_clip wrote to the
# results Volume, unmodified (no reinterpretation, spec item 5).
# ---------------------------------------------------------------------------

def _clip_id_for(job_id: str) -> str:
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    return meta["clip_id"] if meta else job_id.removeprefix("job_")


def _resolve_job(job_id: str) -> tuple[str, str]:
    """(job that actually did the work, its clip_id) for a possibly-aliased id.

    A link that deduplicated at gate 2 or 3 was handed its own job_id before
    the match was known, so that id is an alias. Both reads come from the same
    job-meta document `_clip_id_for` already uses, so an alias costs nothing
    extra -- and the non-alias path never calls this at all (see
    `get_job_status`), which keeps a poll at exactly one Volume read.
    """
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json") or {}
    return (meta.get("canonical_job_id") or job_id,
            meta.get("clip_id") or job_id.removeprefix("job_"))


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
    doc = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
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
        #
        # A missing document is also the only case that can be a dedupe alias
        # (`_alias_to` removes the alias's own status doc precisely so this
        # branch is reached), so the redirection is resolved here too -- off
        # the hot path, where the common "job is genuinely running" poll still
        # costs exactly one Volume read.
        canonical_job, clip_id = _resolve_job(job_id)
        if canonical_job != job_id:
            doc = _volume_read_json(results_volume, f"/{canonical_job}.job-status.json")
            if doc is not None:
                doc = dict(doc, job_id=job_id)
                result = validate_job_status(doc)
                if not result.valid:
                    raise HTTPException(500, f"job-status document failed contract validation: {result.errors}")
                return doc
        _refuse_if_removed(clip_id)
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
def retry_job(job_id: str, background: BackgroundTasks) -> dict:
    doc = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
    if doc is None:
        # A dedupe alias has no status document of its own. Resolving gives the
        # truthful 409 ("succeeded, nothing to retry") instead of a 404 that
        # would claim the caller's job_id never existed.
        canonical_job, _ = _resolve_job(job_id)
        doc = (_volume_read_json(results_volume, f"/{canonical_job}.job-status.json")
               if canonical_job != job_id else None)
    if doc is None:
        raise HTTPException(404, "Unknown job_id.")
    if doc["state"] != "failed":
        raise HTTPException(409, f"Job is '{doc['state']}', not 'failed' -- nothing to retry.")
    if not doc["error"] or not doc["error"]["retryable"]:
        raise HTTPException(409, "This failure is not retryable.")

    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")

    # A link job that failed during the fetch has no clip anywhere -- nothing
    # was ever downloaded. Re-spawning run_clip on it would burn a GPU
    # container looking for a file that does not exist and fail with a
    # confusing "not found", so the retry re-runs the fetch instead. The
    # error's own code is what says which stage failed.
    if (meta or {}).get("source_url") and doc["error"]["code"] in ingest.FETCH_STAGE_CODES:
        link = ingest.normalize(meta["source_url"])
        if link is None:  # pragma: no cover -- it normalised once to get here
            raise HTTPException(500, "The stored link no longer parses -- cannot re-run the fetch.")
        clip_id = meta.get("clip_id") or job_id.removeprefix("job_")
        _refuse_if_removed(clip_id)
        _write_status(job_id, "processing", "Fetching the video", 0.02)
        background.add_task(_ingest_link, link, clip_id, job_id)
        return {"job_id": job_id, "retry_count": doc["retry_count"] + 1}

    if meta is None:
        raise HTTPException(500, "No job-meta record for this job_id -- cannot recover its clip_id.")
    # A removal deletes the source video, so a retry here would burn GPU time
    # on a clip that no longer exists -- and must not put a removed lesson back
    # on its feet even if it somehow could.
    _refuse_if_removed(meta["clip_id"])

    retry_count = doc["retry_count"] + 1
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

    stored = _volume_read_bytes(results_volume, f"/{clip_id}.motion-result.json.gz")
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
# comment: never a signed/expiring URL AS the id -- this endpoint is the
# separate resolution step, and streams bytes directly since there is no S3
# to presign against yet, see the storage-decision docstring above).
# ---------------------------------------------------------------------------

@app.get("/assets/{asset_id:path}")
def get_asset(asset_id: str) -> Response:
    if asset_id.startswith("video:"):
        clip_id = asset_id[len("video:"):]
        _refuse_if_removed(clip_id)
        video = _volume_read_bytes(uploads_volume, f"/{clip_id}.mp4") or _volume_read_bytes(eval_volume, f"/{clip_id}.mp4")
        if video is None:
            raise HTTPException(404, "No video for this asset id.")
        return Response(content=video, media_type="video/mp4")
    if asset_id.endswith(".glb"):
        # `{clip_id}_track{n}.glb`, per modal_app.export_clip_gltf. Checked
        # against the tombstone too: the GLB is the dancer's motion, and a
        # removal that left it individually fetchable would not be a removal.
        _refuse_if_removed(asset_id.rsplit("_track", 1)[0])
        glb = _volume_read_bytes(results_volume, f"/{asset_id}")
        if glb is None:
            raise HTTPException(404, "No GLB for this asset id.")
        return Response(content=glb, media_type="model/gltf-binary")
    raise HTTPException(404, "Unrecognized asset id.")


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
    _TOUCHED.pop(clip_id, None)
    print(f"[removal] {clip_id}: deleted {len(outcome['deleted'])} artifacts ({reason})")
    return RemovalResponse(clip_id=clip_id, removed=outcome["deleted"],
                           already_absent=outcome["already_absent"])


@app.get("/health")
def health() -> dict:
    return {"ok": True}
