"""What a lesson is made of, when it goes away, and how it goes away.

One module because its callers must never disagree about what "deleted" means:

  * `api.py`'s removal endpoint -- a dancer, or an uploader, asking for a
    lesson to be taken down. Immediate.
  * `modal_app.py`'s `sweep_expired` -- the scheduled last-accessed expiry.
  * every writer of a lesson (the GPU stage, export, the beat proposal), which
    checks `ensure_not_removed` before it writes and runs `stop_and_sweep`
    when it finds it was too late.
  * `audit_removed.py --fix`, the owner's re-sweep.

If those ever delete different sets of files, the one that deletes less is
a privacy bug that nobody will notice until someone checks. So the set lives
in one function, `clip_artifact_paths`, and every caller deletes exactly it.

Both use `Volume.remove_file` (the Modal client call) rather than `os.remove`
on a mount, so the same code path runs from the always-on API process and from
inside a scheduled container.

**Why there is a retention policy at all, given the measured numbers.**
Storage is not the reason, and pretending it is would be dishonest. After the
npz is dropped (see `modal_app.py`), one solo lesson is about 4.1 MB:

    MotionResult, gzipped   1.49 MB     (was: a 61.30 MB npz, read on every request)
    GLB, per dancer         1.53 MB
    source video            1.10 MB

At Modal's $0.09/GiB/month with 1 TiB/month free, that is $0.00035 per lesson
per month -- so a lesson costs less to store for TWENTY YEARS than it costs to
reconstruct once ($0.0839 measured on solo-01, L40S). A short TTL is
economically irrational: every expiry that the learner then re-uploads spends
two decades of storage to save nothing.

The reason to expire is the one in docs/legal/rights-and-privacy.md section 1:
the system holds video of people who never agreed to be here, and holding it
after it has stopped being useful to anyone is exposure with no upside. So the
clock runs on LAST ACCESS, not on upload: a lesson people keep opening is a
lesson that is doing its job, and a lesson nobody has opened in six months is
one nobody will miss.
"""
from __future__ import annotations

import time

# Days since a lesson was last opened before it is swept. Justified on privacy,
# not cost (see module docstring) -- so the number is chosen as "comfortably
# longer than a learner's plausible gap", not as "as short as we can bear".
# Six months covers a season away from dancing and a summer break. This is
# explicitly the builder's call to change (docs/legal/rights-and-privacy.md
# section 8: "pick a number, state it, honour it") -- but if it changes, the
# copy in docs/DESIGN.md section 7d changes in the same commit, or the product
# is making a promise the code does not keep (DESIGN.md section 7h).
TTL_DAYS = 180

# ponytail: no hard ceiling on total age, deliberately. A "delete at 2 years no
# matter what" rule would take a lesson away from someone who is actively using
# it, for a privacy gain that last-access expiry already delivers -- the clips
# that linger are the ones being opened. Add one if the retention promise ever
# needs to name a maximum.


def tombstone_path(clip_id: str) -> str:
    return f"/{clip_id}.removed.json"


# --- the tombstone as a stop sign -------------------------------------------
#
# job_6037... (and its siblings 66d7..., 11f6..., found by the audit): a lesson
# was removed and then its bytes came back, because nothing that WRITES a
# lesson ever looked at the tombstone. The API refused to serve them (410), but
# the upload, the job record, the npz, the performance record, the job status
# and even a GLB sat on the Volumes, derived from a video someone had asked us
# to delete. So every writer asks this one question at its safe points -- here,
# in one place, so the answer cannot drift between the API, the GPU worker, the
# exporter and the beat proposal.

class Removed(Exception):
    """This lesson was taken down; stop, write nothing more, and do not report
    it as a failure. The tombstone is the only record a removal leaves."""


def is_removed(results_volume, clip_id: str, reload: bool = False) -> bool:
    """True once `{clip_id}.removed.json` exists.

    Read through the client API (`read_file_into_fileobj`), not a mount path,
    so the answer is the server's committed state: the removal endpoint writes
    the tombstone with `batch_upload`, and a mount snapshot taken before that
    would still say "not removed". `reload=True` additionally refreshes the
    container's mount, for callers that go on to read other files through it
    (Volumes are eventually consistent; see run_clip's uploads.reload()).
    It is best-effort: reload() refuses while files are open, and the check
    itself does not depend on it.
    """
    if reload:
        try:
            results_volume.reload()
        except Exception as e:  # noqa: BLE001
            print(f"[removal] reload before tombstone check failed ({type(e).__name__}: {e})")
    return read_json(results_volume, tombstone_path(clip_id)) is not None


def ensure_not_removed(results_volume, clip_id: str, reload: bool = False) -> None:
    """Raise `Removed` if the lesson was taken down. Call it before starting
    work and before every durable write or commit."""
    if is_removed(results_volume, clip_id, reload):
        raise Removed(clip_id)


def write_tombstone(results_volume, clip_id: str, reason: str,
                    relationship: str | None = None) -> bool:
    """Write the tombstone if there is none yet. True if this call wrote it.

    An existing one is never rewritten: its timestamp and the requester's
    reason are the record, and a later sweep must not overwrite them.
    """
    if is_removed(results_volume, clip_id):
        return False
    tomb = {"clip_id": clip_id, "removed_at": time.time(), "reason": reason}
    if relationship:
        tomb["relationship"] = relationship
    write_json(results_volume, tombstone_path(clip_id), tomb)
    return True


def clip_artifact_paths(results_listing: list[str], clip_id: str, job_id: str | None) -> dict:
    """Every stored byte belonging to one lesson, split by which Volume it is on.

    `results_listing` is the flat list of filenames in the results Volume root
    (from `Volume.listdir`), needed because the per-dancer GLB names depend on
    ByteTrack's track ids and, since GLBs are versioned, on their bytes -- none
    of which are knowable from the clip_id alone.

    Deliberately includes artifacts that may not exist: the callers ignore
    FileNotFoundError, and a list that is a superset of reality is safe while
    a list that misses a file is the bug this module exists to prevent. For the
    same reason anything in the listing named after the clip or its job goes
    too, so an artifact added later is covered without editing this list.
    """
    results = [
        f"/{clip_id}.npz",                      # dropped after export now, but old lessons have one
        f"/{clip_id}.motion-result.json.gz",    # the materialised contract document
        f"/{clip_id}.export-manifest.json",
        f"/{clip_id}.performance.json",
        # The beat proposal. Derived from the audio of a person's video, so it
        # goes with everything else -- D7's promise is kept by this list.
        f"/{clip_id}.beats.json",
        # The detector's 2D keypoints of the person in the clip (milestones.py).
        f"/{clip_id}.detections.json",
        f"/{clip_id}.last-access.json",
    ]
    job_ids = {j for j in (job_id, f"job_{clip_id}") if j}
    for j in sorted(job_ids):
        results += [f"/{j}.job-status.json", f"/{j}.job-meta.json"]
    # Every dancer's GLB, every version (`{clip_id}_track{n}[.{hash}].glb`),
    # and anything else keyed by the clip or its job. Never the tombstone.
    prefixes = (f"{clip_id}.", f"{clip_id}_track") + tuple(f"{j}." for j in job_ids)
    results += [f"/{name}" for name in results_listing
                if name.startswith(prefixes) and f"/{name}" != tombstone_path(clip_id)]
    return {
        "uploads": [f"/{clip_id}.mp4"],   # the source video: the thing a dancer actually wants gone
        "results": list(dict.fromkeys(results)),
    }


def _delete_r2_objects(clip_id: str) -> list[str]:
    """The same lesson, in the other place its bytes live.

    Delivered artifacts moved to R2 (storage.py). A deletion path that knows
    about only one of the two storage systems is not a storage leak, it is a
    privacy leak: the dancer asked for the video to be gone and the video is
    exactly what R2 is holding. So it goes here, inside the one function both
    the takedown endpoint and the sweeper call, for the same reason
    `clip_artifact_paths` is one function.

    Listed by prefix rather than derived from the Volume: GLBs and the
    MotionResult are versioned by their bytes, and an old version can exist
    only in R2.

    Returns `r2:<key>` entries so the caller's report distinguishes them from
    Volume paths. Best-effort: an R2 failure must not stop the Volume deletion
    that already happened, but it is printed rather than swallowed, because an
    object left in R2 after a takedown is the failure that matters most here.

    **Not done, and named rather than hidden:** with a CDN in front, deleting
    the origin object does not delete the edge copy (infrastructure.md §9, D7).
    There is no custom domain yet, so there is no edge copy yet -- today's
    presigned URLs read through to the origin. When `R2_PUBLIC_BASE_URL` is set
    this function must also issue a Cloudflare cache purge for the same keys,
    and that needs an API token that does not exist yet. Tracked in
    docs/DEPLOYMENT.md as a blocking item on the custom-domain cutover.
    """
    try:
        import storage
    except ImportError:  # storage.py not on the path (a caller that predates it)
        return []
    if not storage.enabled():
        return []
    out = []
    try:
        keys = storage.clip_keys(clip_id)
    except Exception as e:  # noqa: BLE001
        print(f"[removal] WARNING: could not list R2 objects of {clip_id}: {e}")
        return []
    for key in keys:
        try:
            storage.client().delete_object(Bucket=storage.bucket(), Key=key)
            out.append(f"r2:{key}")
        except Exception as e:  # noqa: BLE001
            print(f"[removal] WARNING: could not delete r2:{key}: {e}")
    return out


def remove_if_present(volume, path: str) -> bool:
    """`Volume.remove_file`, answering False for a file that is not there.

    The client maps a server NotFoundError to FileNotFoundError, but for a
    missing file on these Volumes the server answers InvalidError("No such
    file or directory.") -- measured against modal 1.5.5, 2026-09-25. Catching
    only FileNotFoundError made the FIRST absent artifact abort the whole
    deletion: a lesson never opened has no `.last-access.json`, an older one no
    `.detections.json`, a reaped one no `.npz`. Anything else still raises.
    """
    try:
        volume.remove_file(path)
        return True
    except FileNotFoundError:
        return False
    except Exception as e:  # noqa: BLE001 -- narrowed by the message just below
        if "No such file" in str(e):
            return False
        raise


def _forget_jobs(clip_id: str, job_id: str | None) -> None:
    """The Postgres job rows. jobstore is imported lazily: the worker images do
    not ship psycopg, and there it has nothing to do anyway (no DATABASE_URL)."""
    try:
        import jobstore
    except ImportError:
        return
    jobstore.forget(job_id or f"job_{clip_id}", clip_id)


def delete_clip(uploads_volume, results_volume, clip_id: str, job_id: str | None,
                reason: str, relationship: str | None = None) -> dict:
    """Remove every artifact of one lesson and leave a tombstone.

    Returns what was actually deleted, so the caller can report it rather than
    claim it -- "we deleted your lesson" is a promise, and DESIGN.md section 7h
    applies to promises about data exactly as it applies to copy.

    The tombstone (`{clip_id}.removed.json`) holds a timestamp, a reason and,
    for a takedown, the requester's relationship category -- nothing else: no
    hashes, no pose, no frames, nothing derived from the video. The reason is
    "expired" for the sweeper and the requester's own optional words for a
    takedown; it is the one field a person typed, and it stays here only. It
    exists so that `GET /jobs/{job_id}` can answer 410 Gone ("this was
    removed") instead of 404 ("never existed"), and so every writer stops
    (`ensure_not_removed`).

    **Written FIRST, and idempotent.** The tombstone used to be written last,
    so that no tombstone ever claimed a lesson gone while bytes remained. That
    left a window in which a running job saw no tombstone and wrote its files
    after they had been deleted (job_6037...). Now it goes first -- every
    reader already answers 410 from that instant, and every writer stops at its
    next check -- and the whole function is safe to run again: an existing
    tombstone is kept, and whatever a late writer managed to put back is
    deleted by the next call (the writers make that call themselves when they
    notice; `audit_removed.py --fix` makes it for anything else).
    """
    write_tombstone(results_volume, clip_id, reason, relationship)

    try:
        listing = [e.path.lstrip("/") for e in results_volume.listdir("/")]
    except Exception:  # noqa: BLE001 -- an unreadable listing must not block deletion
        listing = []

    paths = clip_artifact_paths(listing, clip_id, job_id)
    deleted, missing = [], []
    for volume, key in ((uploads_volume, "uploads"), (results_volume, "results")):
        for path in paths[key]:
            (deleted if remove_if_present(volume, path) else missing).append(path)

    deleted += _delete_r2_objects(clip_id)
    remove_fingerprint(results_volume, clip_id)
    _forget_jobs(clip_id, job_id)

    # No .commit() anywhere in here, deliberately. `remove_file` and
    # `batch_upload` are client API calls -- the bytes are already gone, or
    # already written, server-side. `Volume.commit()` is only for flushing
    # writes made through a MOUNT from inside a container, and calling it from
    # the API process raises "commit() can only be called on a mounted volume
    # inside a container" -- which here would mean a 500 returned to someone
    # after their lesson had, in fact, been deleted. Verified against the real
    # client, not assumed.
    return {"clip_id": clip_id, "deleted": deleted, "already_absent": missing}


def stop_and_sweep(uploads_volume, results_volume, clip_id: str, job_id: str | None,
                   mounts: dict | None = None) -> dict:
    """What a worker does when `Removed` stops it: take back anything it (or a
    racing writer) put down after the removal, and report nothing else -- no
    `failed` status, the tombstone stays the only record.

    `mounts` ({mount_dir: volume}) are this container's own mounts. Their
    uncommitted writes are deleted locally and committed first: Modal commits a
    mounted Volume in the background and again when the container exits, so a
    file written but not yet committed would otherwise land AFTER the
    server-side sweep below and survive it.
    """
    import os
    swept = []
    for mount, volume in (mounts or {}).items():
        try:
            paths = clip_artifact_paths(os.listdir(mount), clip_id, job_id)
            for path in sorted(set(paths["uploads"]) | set(paths["results"])):
                if os.path.exists(mount + path):
                    os.remove(mount + path)
                    swept.append(path)
            volume.commit()
        except Exception as e:  # noqa: BLE001 -- the server-side sweep below still runs
            print(f"[removal] local sweep of {mount} failed ({type(e).__name__}: {e})")
    swept += delete_clip(uploads_volume, results_volume, clip_id, job_id, "")["deleted"]
    print(f"[removal] {clip_id} was removed while this ran: stopped, swept {swept}")
    return {"clip_id": clip_id, "removed": True, "swept": swept}


# --- fingerprint index ------------------------------------------------------
#
# ponytail: ONE json file, read-and-rewritten whole. At ~640 bytes an entry
# that is 64 KB at 100 lessons and 64 MB at 100k, and two uploads landing at
# the same moment can lose one entry. Both failure modes are benign in this
# direction: a lost or stale entry means the next upload of that clip is
# reconstructed again ($0.08), never that the wrong lesson is served -- every
# candidate is re-verified against a live, succeeded job before it is used.
# Upgrade path when it stops being cheap: one row per clip in any real
# key-value store, keyed on sha256, scanned on the dHash prefix.

INDEX_PATH = "/fingerprints/index.json"


def read_json(volume, path: str) -> dict | None:
    import io
    import json
    try:
        buf = io.BytesIO()
        volume.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return json.loads(buf.getvalue())


def read_index(results_volume) -> list[dict]:
    doc = read_json(results_volume, INDEX_PATH)
    return doc.get("entries", []) if doc else []


def write_index(results_volume, entries: list[dict]) -> None:
    write_json(results_volume, INDEX_PATH, {"entries": entries})


def remove_fingerprint(results_volume, clip_id: str) -> None:
    """Drop this clip's fingerprint so a later re-upload is not matched to a
    lesson that no longer exists.

    Note what this deliberately does NOT do: it does not keep the fingerprint
    as a blocklist to refuse future uploads of the same video. That would be
    more effective at keeping removed content off the platform, and it would
    mean retaining a derivative of exactly the content someone asked us to
    delete. Deleting it is the answer that matches what was promised; the
    consequence -- a re-upload is reconstructed afresh -- is recorded in
    docs/OPEN-DECISIONS.md D7.
    """
    entries = read_index(results_volume)
    kept = [e for e in entries if e.get("clip_id") != clip_id]
    # Only when there is something to drop: a repeat sweep must not rewrite the
    # whole index (and race a concurrent upload's entry) for nothing.
    if len(kept) != len(entries):
        write_index(results_volume, kept)


# --- last access ------------------------------------------------------------

def touch_path(clip_id: str) -> str:
    return f"/{clip_id}.last-access.json"


def is_expired(last_access_s: float, now_s: float | None = None) -> bool:
    return ((now_s if now_s is not None else time.time()) - last_access_s) > TTL_DAYS * 86400


def write_json(volume, path: str, doc: dict) -> None:
    """Write one small JSON document to a Volume from outside a container.

    batch_upload takes files, not bytes, so this round-trips through a temp
    file. Fine for the handful of small documents here; never use it for
    anything on a hot path.
    """
    import json
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        with volume.batch_upload(force=True) as batch:
            batch.put_file(tmp, path)
    finally:
        os.unlink(tmp)
