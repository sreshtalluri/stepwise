"""What a lesson is made of, when it goes away, and how it goes away.

One module because there are exactly two callers and they must never disagree
about what "deleted" means:

  * `api.py`'s removal endpoint -- a dancer, or an uploader, asking for a
    lesson to be taken down. Immediate.
  * `modal_app.py`'s `sweep_expired` -- the scheduled last-accessed expiry.

If those two ever delete different sets of files, the one that deletes less is
a privacy bug that nobody will notice until someone checks. So the set lives
in one function, `clip_artifact_paths`, and both callers delete exactly it.

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

The reason to expire is the one in docs/research/rights-and-privacy.md section 1:
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
# explicitly the builder's call to change (docs/research/rights-and-privacy.md
# section 8: "pick a number, state it, honour it") -- but if it changes, the
# copy in docs/DESIGN.md section 7d changes in the same commit, or the product
# is making a promise the code does not keep (DESIGN.md section 7h).
TTL_DAYS = 180

# ponytail: no hard ceiling on total age, deliberately. A "delete at 2 years no
# matter what" rule would take a lesson away from someone who is actively using
# it, for a privacy gain that last-access expiry already delivers -- the clips
# that linger are the ones being opened. Add one if the retention promise ever
# needs to name a maximum.


def clip_artifact_paths(results_listing: list[str], clip_id: str, job_id: str | None) -> dict:
    """Every stored byte belonging to one lesson, split by which Volume it is on.

    `results_listing` is the flat list of filenames in the results Volume root
    (from `Volume.listdir`), needed because the per-dancer GLB names depend on
    ByteTrack's track ids, which are not knowable from the clip_id alone.

    Deliberately includes artifacts that may not exist: the callers ignore
    FileNotFoundError, and a list that is a superset of reality is safe while
    a list that misses a file is the bug this module exists to prevent.
    """
    results = [
        f"/{clip_id}.npz",                      # dropped after export now, but old lessons have one
        f"/{clip_id}.motion-result.json.gz",    # the materialised contract document
        f"/{clip_id}.export-manifest.json",
        f"/{clip_id}.performance.json",
        f"/{clip_id}.last-access.json",
    ]
    # Every dancer's GLB. `{clip_id}_track{n}.glb` per modal_app.export_clip_gltf.
    results += [
        f"/{name}" for name in results_listing
        if name.startswith(f"{clip_id}_track") and name.endswith(".glb")
    ]
    if job_id:
        results += [f"/{job_id}.job-status.json", f"/{job_id}.job-meta.json"]
    return {
        "uploads": [f"/{clip_id}.mp4"],   # the source video: the thing a dancer actually wants gone
        "results": results,
    }


def delete_clip(uploads_volume, results_volume, clip_id: str, job_id: str | None,
                reason: str) -> dict:
    """Remove every artifact of one lesson and leave a tombstone.

    Returns what was actually deleted, so the caller can report it rather than
    claim it -- "we deleted your lesson" is a promise, and DESIGN.md section 7h
    applies to promises about data exactly as it applies to copy.

    The tombstone (`{clip_id}.removed.json`) holds a timestamp and a reason
    category and nothing else: no hashes, no pose, no frames, nothing derived
    from the person. It exists so that `GET /jobs/{job_id}` can answer 410 Gone
    ("this was removed") instead of 404 ("never existed"), which is both more
    honest and more useful to whoever is holding the link.
    """
    try:
        listing = [e.path.lstrip("/") for e in results_volume.listdir("/")]
    except Exception:  # noqa: BLE001 -- an unreadable listing must not block deletion
        listing = []

    paths = clip_artifact_paths(listing, clip_id, job_id)
    deleted, missing = [], []
    for volume, key in ((uploads_volume, "uploads"), (results_volume, "results")):
        for path in paths[key]:
            try:
                volume.remove_file(path)
                deleted.append(path)
            except FileNotFoundError:
                missing.append(path)

    remove_fingerprint(results_volume, clip_id)

    # Written last, on purpose: if anything above raised, there is no tombstone
    # claiming the lesson is gone while its bytes are still sitting there.
    #
    # No .commit() anywhere in here, deliberately. `remove_file` and
    # `batch_upload` are client API calls -- the bytes are already gone, or
    # already written, server-side. `Volume.commit()` is only for flushing
    # writes made through a MOUNT from inside a container, and calling it from
    # the API process raises "commit() can only be called on a mounted volume
    # inside a container" -- which here would mean a 500 returned to someone
    # after their lesson had, in fact, been deleted. Verified against the real
    # client, not assumed.
    write_json(results_volume, f"/{clip_id}.removed.json", {
        "clip_id": clip_id,
        "removed_at": time.time(),
        "reason": reason,
    })
    return {"clip_id": clip_id, "deleted": deleted, "already_absent": missing}


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
    entries = [e for e in read_index(results_volume) if e.get("clip_id") != clip_id]
    write_index(results_volume, entries)


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
