"""Retention, deletion, and the takedown path.

Before this file there was no deletion, expiry or retention code anywhere in
the service: nothing was ever removed, and the landing mockup's promise "we
keep the clip while the lesson exists" (docs/OPEN-DECISIONS.md D6) was untrue
in both directions. This is the code that makes it true.

Deliberately depends on nothing but stdlib + the modal client, so both the
FastAPI service (api.py) and the scheduled sweeper inside Modal
(modal_app.py::sweep_expired) can call exactly the same deletion routine.
Two implementations of "delete a lesson" is how one of them silently stops
deleting something.

THE INDEX
---------
One `modal.Dict`, `stepwise-clip-index`, keyed by canonical clip_id. Modal's
Dict is a platform primitive, so this adds no infrastructure and no
credentials. One record per distinct piece of *content*, not per upload:

    {
      "clip_id":        str,          # canonical: the first upload of this content
      "fingerprint":    {...},        # fingerprint.py record, ~2.7 kB for a 60 s clip
      "created_at":     float,        # epoch seconds
      "last_accessed":  float,        # bumped by result/asset reads -- this is what TTL uses
      "job_ids":        [str, ...],   # every job that resolved here. Dedupe's whole point:
                                      # one removal covers all of them.
      "removed_at":     float|None,
      "removed_reason": "takedown"|"expired"|None,
    }

WHAT THIS DELIBERATELY IS NOT
-----------------------------
There is no endpoint, function or field here that lists, searches or browses
the index. The only way to reach a record is to already hold either the
fingerprint of a video you just uploaded, or a job_id someone gave you. That
is a product and legal decision, not an oversight: storage "at the direction
of a user" and a curated library of other people's dances are different things
under the DMCA analysis in docs/research/rights-and-privacy.md §3d, and the
technical distance between them is about fifteen lines. `Dict.items()` is
called in exactly two places (duplicate lookup and the sweeper), both
server-side, and neither returns anything derived from it to a caller.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

import modal

INDEX_NAME = "stepwise-clip-index"

# Last-accessed TTL. Justification and the storage arithmetic behind it are in
# docs/research/dedupe-measurements.md; the short version is that this is a
# privacy and honesty policy, not a cost one. Measured: a stripped lesson is
# 3.7 MB, Modal volumes bill $0.09/GiB/month, so one lesson-month costs
# $0.0003 against $0.0839 to reconstruct the clip again -- storage is ~273x
# cheaper than recompute, and an aggressive TTL would be economically absurd.
# Six months untouched is the point at which someone is genuinely finished
# with a dance, and it is short enough to state plainly on the landing page.
TTL_DAYS = 180
_TTL_S = TTL_DAYS * 24 * 3600

# Bumping last_accessed writes to the Dict. ponytail: debounced to one write
# per hour per clip rather than one per request; TTL granularity is 180 days,
# so an hour of staleness cannot expire anything that is in use.
ACCESS_WRITE_DEBOUNCE_S = 3600


@functools.lru_cache(maxsize=1)
def index() -> modal.Dict:
    """The handle is a client-side reference, not a snapshot -- every get/put
    still round-trips -- so caching it just avoids re-resolving the name on
    every request."""
    return modal.Dict.from_name(INDEX_NAME, create_if_missing=True)


def new_record(clip_id: str, fp_record: dict, job_id: str) -> dict:
    now = time.time()
    return {
        "clip_id": clip_id,
        "fingerprint": fp_record,
        "created_at": now,
        "last_accessed": now,
        "job_ids": [job_id],
        "removed_at": None,
        "removed_reason": None,
    }


def touch(idx: modal.Dict, clip_id: str) -> None:
    """Mark a lesson as still in use. Silent no-op for a clip with no record
    (an eval clip run straight through modal_app.py never had one)."""
    rec = idx.get(clip_id)
    if rec is None or rec.get("removed_at"):
        return
    now = time.time()
    if now - rec.get("last_accessed", 0) < ACCESS_WRITE_DEBOUNCE_S:
        return
    rec["last_accessed"] = now
    idx.put(clip_id, rec)


def _try_remove(volume: modal.Volume, path: str, deleted: list[str]) -> None:
    try:
        volume.remove_file(path)
        deleted.append(path)
    except (FileNotFoundError, Exception) as exc:  # noqa: BLE001
        # A missing file is the normal case (a refused job never wrote a GLB).
        # Anything else is worth seeing in the log, but must not abort the rest
        # of the purge -- a takedown that stops halfway is the worst outcome
        # here, strictly worse than a noisy log.
        if not isinstance(exc, FileNotFoundError):
            print(f"[retention] could not remove {path}: {exc!r}")


def purge_clip(
    clip_id: str,
    reason: str,
    *,
    uploads_volume: modal.Volume,
    results_volume: modal.Volume,
    idx: Optional[modal.Dict] = None,
    extra_job_ids: Iterable[str] = (),
) -> dict:
    """Delete every artifact belonging to one canonical clip, everywhere.

    This is the whole takedown mechanism and the whole expiry mechanism. It is
    one function because "removed" must mean the same thing however it was
    triggered.

    What survives on purpose, and only this:
      * the index record, tombstoned. It holds the perceptual fingerprint
        (~2.7 kB of hashes, not video) so that re-uploading the same clip after
        a takedown is refused instead of silently resurrecting it. A removal
        that can be undone by re-uploading is not a removal.
      * a `{job_id}.removed.json` marker per job, so every share link that
        pointed here answers "gone" instead of reading as a job that never
        started. Deleting the job-status file alone would make api.py's
        not-found branch report the lesson as `queued` forever, which is a
        false statement about our own data (DESIGN.md §7h).
    """
    idx = idx if idx is not None else index()
    rec = idx.get(clip_id)
    job_ids = list(dict.fromkeys(list(rec["job_ids"]) + list(extra_job_ids))) if rec else list(extra_job_ids)

    deleted: list[str] = []
    _try_remove(uploads_volume, f"/{clip_id}.mp4", deleted)

    # Every GLB for this clip. Named `{clip_id}_track{n}.glb` by
    # export_clip_gltf, but the manifest is the authority on which exist --
    # fall back to a listdir so a manifest that failed to write cannot leave
    # orphaned meshes behind.
    glbs: list[str] = []
    try:
        import io
        import json as _json
        buf = io.BytesIO()
        results_volume.read_file_into_fileobj(f"/{clip_id}.export-manifest.json", buf)
        glbs = list(_json.loads(buf.getvalue()).get("glb_paths", {}).values())
    except Exception:  # noqa: BLE001 -- no manifest is a normal state for a refused job
        pass
    try:
        listed = [e.path for e in results_volume.listdir("/")]
    except Exception:  # noqa: BLE001
        listed = []
    glbs += [p.lstrip("/") for p in listed
             if p.lstrip("/").startswith(f"{clip_id}_track") and p.endswith(".glb")]

    for name in dict.fromkeys(glbs):
        _try_remove(results_volume, f"/{name}", deleted)

    for suffix in (".npz", ".export-manifest.json", ".performance.json"):
        _try_remove(results_volume, f"/{clip_id}{suffix}", deleted)

    now = time.time()
    for job_id in job_ids:
        _try_remove(results_volume, f"/{job_id}.job-status.json", deleted)
        _try_remove(results_volume, f"/{job_id}.job-meta.json", deleted)
    if job_ids:
        _write_removal_markers(results_volume, job_ids, clip_id, reason, now)

    if rec is not None:
        rec["removed_at"] = now
        rec["removed_reason"] = reason
        rec["job_ids"] = job_ids
        idx.put(clip_id, rec)

    print(f"[retention] purged {clip_id} ({reason}): {len(deleted)} files, {len(job_ids)} job(s)")
    return {"clip_id": clip_id, "reason": reason, "files_deleted": deleted, "job_ids": job_ids}


def _write_removal_markers(results_volume: modal.Volume, job_ids: list[str],
                           clip_id: str, reason: str, when: float) -> None:
    import json
    import os
    import tempfile

    paths = []
    try:
        with results_volume.batch_upload(force=True) as batch:
            for job_id in job_ids:
                fd, tmp = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, "w") as f:
                    json.dump({"job_id": job_id, "clip_id": clip_id,
                               "reason": reason, "removed_at": when}, f)
                paths.append(tmp)
                batch.put_file(tmp, f"/{job_id}.removed.json")
    finally:
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def removal_marker(results_volume: modal.Volume, job_id: str) -> Optional[dict]:
    import io
    import json
    buf = io.BytesIO()
    try:
        results_volume.read_file_into_fileobj(f"/{job_id}.removed.json", buf)
    except FileNotFoundError:
        return None
    return json.loads(buf.getvalue())


def sweep(uploads_volume: modal.Volume, results_volume: modal.Volume,
          *, now: Optional[float] = None, ttl_s: int = _TTL_S) -> dict:
    """Delete every lesson not opened in TTL_DAYS. Called from a Modal cron."""
    now = now if now is not None else time.time()
    idx = index()
    expired, kept = [], 0
    for clip_id, rec in list(idx.items()):
        if rec.get("removed_at"):
            continue
        if now - rec.get("last_accessed", rec.get("created_at", now)) > ttl_s:
            purge_clip(clip_id, "expired", uploads_volume=uploads_volume,
                       results_volume=results_volume, idx=idx)
            expired.append(clip_id)
        else:
            kept += 1
    print(f"[retention] sweep: {len(expired)} expired, {kept} still within {ttl_s // 86400} days")
    return {"expired": expired, "kept": kept}
