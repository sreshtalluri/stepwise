"""Where a job's status lives. One interface, two backends, chosen by env var.

`{job_id}.job-status.json` on a Modal Volume was always provisional --
`modal_app.py`'s own comment says so. The reason it has to move is not tidiness
(infrastructure.md decision 4 and §4): **Modal Volumes are commit-based and
eventually consistent.** `run_clip` already carries a `uploads.reload()`
workaround for a real race, with the comment "this is a Volume, not a queue --
no delivery guarantee beyond eventually consistent". A status document polled
every two seconds is precisely a read-after-write workload, and that substrate
does not promise one.

**What must not change, and does not.** `GET /jobs/{job_id}` serves the same
`job-status.schema.json` document either way -- same seven fields, same
`schema_version`, same values. `apps/web/lib/jobStatus.ts` and
`ProcessingScreen.tsx` keep working byte-for-byte, and nothing above the HTTP
boundary knows this file exists. `.spawn()` is still the queue; no queue,
pub/sub, WebSocket or SSE is introduced here.

**Selection, and therefore rollback:**

    STEPWISE_JOB_BACKEND unset | "volume"   -> the results Volume. Today's
                                               behaviour, unchanged.
    STEPWISE_JOB_BACKEND = "postgres"       -> the `jobs` table, with the
                                               Volume as a read-through source.

Cutover is setting one variable; rollback is unsetting it. Neither is a deploy
of different code, which is the only property that makes a storage swap safe to
do on a service that is already serving someone.

**Why postgres mode still reads the Volume.** This is infrastructure.md
migration step 3, not step 4: the GPU worker still writes the Volume JSON, and
the API reconciles -- it reads the row, and on a miss reads the Volume document
and writes the row through. That has three properties worth the extra read:
a job already in flight at cutover keeps reporting correctly, a rollback loses
nothing because the Volume copy was never stopped, and the database becomes the
source of truth one job at a time instead of in one jump.

Step 4 -- the worker writing Postgres directly and the Volume write being
deleted -- is deliberately **not** done here. It means adding `psycopg` to the
two pinned GPU images, which took seven environment bugs to get green
(docs/GATE-REPORT.md G3), in exchange for removing a read from a path that is
already correct. infrastructure.md §5 says to do it after a week of clean
production polling; there has not yet been a day. The exact change is written
down in docs/DEPLOYMENT.md instead of guessed at here.
"""
from __future__ import annotations

import json
import os
from typing import Optional

SCHEMA_VERSION = "1.0.0"


def backend() -> str:
    """Read per call, not cached: Modal injects Secrets into the environment,
    and a value captured at import would freeze whatever was true before that."""
    return (os.environ.get("STEPWISE_JOB_BACKEND") or "volume").strip().lower()


def postgres_enabled() -> bool:
    return backend() == "postgres" and bool(os.environ.get("DATABASE_URL"))


def status_doc(job_id: str, row: dict) -> dict:
    """One row -> one job-status.schema.json document.

    The field order matches what `run_clip::write_status` writes, so a diff of
    the two responses is empty rather than merely equivalent.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": row["state"],
        "stage_message": row["stage_message"] or "",
        "progress": row["progress"],
        "error": row["error"],
        "retry_count": row["retry_count"],
    }


def queued_doc(job_id: str) -> dict:
    """A job that has been spawned but has not written its first document yet.

    Not a 404: that is a real, valid state. Kept here so both backends answer
    it identically.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": "queued",
        "stage_message": "",
        "progress": None,
        "error": None,
        "retry_count": 0,
    }


# --- postgres --------------------------------------------------------------

_pool = None


def connection():
    """One lazily-created connection pool. `DATABASE_URL` must be the **pooled**
    Neon string: this API scales to zero and back up, so the thing on the other
    end has to tolerate connections appearing and vanishing in bursts."""
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=0, max_size=4,
                               open=True, kwargs={"autocommit": True})
    return _pool.connection()


def _pg_read(job_id: str) -> Optional[dict]:
    with connection() as conn:
        row = conn.execute(
            "SELECT state, stage_message, progress, error, retry_count "
            "FROM jobs WHERE job_id = %s", (job_id,)).fetchone()
    if row is None:
        return None
    state, stage_message, progress, error, retry_count = row
    return status_doc(job_id, {"state": state, "stage_message": stage_message,
                               "progress": progress, "error": error,
                               "retry_count": retry_count})


def _pg_write(job_id: str, clip_id: str, doc: dict, insert: bool = True) -> None:
    """Upsert, last-write-wins on `updated_at`.

    Deliberately not a compare-and-set on state: `run_clip` emits its stages in
    order from a single worker, so there is one writer per job and ordering is
    already guaranteed upstream. A CAS here would only add a way to drop a
    legitimate update.

    `insert=False` updates an existing row and never creates one: the mirror
    uses it for a row it has just read, so a removal that deletes the row in
    between (forget) wins instead of being undone by the write.
    """
    args = (doc["state"], doc["stage_message"], doc["progress"],
            json.dumps(doc["error"]) if doc["error"] else None, doc["retry_count"])
    with connection() as conn:
        if not insert:
            conn.execute(
                "UPDATE jobs SET state = %s, stage_message = %s, progress = %s, error = %s, "
                "retry_count = %s, updated_at = now() WHERE job_id = %s", args + (job_id,))
            return
        conn.execute(
            "INSERT INTO jobs (job_id, clip_id, state, stage_message, progress, error, retry_count) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (job_id) DO UPDATE SET "
            "  state = EXCLUDED.state, stage_message = EXCLUDED.stage_message, "
            "  progress = EXCLUDED.progress, error = EXCLUDED.error, "
            "  retry_count = EXCLUDED.retry_count, updated_at = now()",
            (job_id, clip_id) + args)


# --- the interface api.py calls -------------------------------------------

def read_status(volume, job_id: str, clip_id_for) -> Optional[dict]:
    """The job's current status document, or None if nothing has been written.

    `volume` is the results Volume and `clip_id_for` resolves a job_id to its
    clip_id -- both passed in rather than imported, so this module never needs
    a Modal handle of its own and stays unit-testable without one.
    """
    import retention

    if not postgres_enabled():
        return retention.read_json(volume, f"/{job_id}.job-status.json")

    row = _pg_read(job_id)
    if row is not None and row["state"] in ("succeeded", "failed"):
        return row
    # Read-through. The worker is still writing the Volume during the migration
    # (see module docstring), so the row alone is never enough for a live job:
    # record_dispatch inserts it as `queued` and nothing but this read ever
    # moves it on. (Returning the row whenever one existed left every job since
    # the cutover reporting `queued` forever.) The Volume doc wins unless it is
    # from an earlier attempt -- record_retry bumps the row's retry_count
    # before the worker has overwritten the old `failed` document.
    doc = retention.read_json(volume, f"/{job_id}.job-status.json")
    if doc is None or (row is not None and doc.get("retry_count", 0) < row["retry_count"]):
        return row
    # `milestones` is display-only and has no column: compare without it, or
    # every poll of a job that carries one would rewrite an unchanged row.
    if {k: v for k, v in doc.items() if k != "milestones"} != row:
        # No row at all is what a removal leaves (forget deleted it), and a
        # worker may still have written the Volume document after that. Copying
        # it back would resurrect the job row of a removed lesson on the next
        # poll, so a missing row is mirrored only once the tombstone says no.
        # A row that exists is a live job's -- the common path pays nothing --
        # and is only UPDATEd, so a removal that deletes it meanwhile wins.
        if row is None and retention.is_removed(volume, clip_id_for(job_id)):
            return doc
        try:
            _pg_write(job_id, clip_id_for(job_id), doc, insert=row is None)
        except Exception as e:  # noqa: BLE001
            # Serving the learner their status matters more than the mirror
            # succeeding; the next poll retries it two seconds from now.
            print(f"[jobstore] could not mirror {job_id} into postgres: {e}")
    return doc


def record_dispatch(volume, job_id: str, clip_id: str, credit: Optional[dict] = None) -> None:
    """Called once, when a job is spawned. Writes the job -> clip mapping that
    retry and result-building need later without parsing it back out of the
    job_id string, and for a pasted link the creator credit (ingest.credit)
    that GET /jobs/{job_id}/source serves."""
    import retention

    meta = {"clip_id": clip_id}
    if credit:
        meta["credit"] = credit
    retention.write_json(volume, f"/{job_id}.job-meta.json", meta)
    if postgres_enabled():
        try:
            _pg_write(job_id, clip_id, queued_doc(job_id))
        except Exception as e:  # noqa: BLE001 -- the Volume record is authoritative until step 4
            print(f"[jobstore] could not insert {job_id}: {e}")


def record_retry(volume, job_id: str, clip_id: str, retry_count: int) -> None:
    """A retried job stays at its job_id and moves back to `queued`,
    incrementing retry_count, rather than minting a new id -- the schema's own
    wording, kept true in both backends."""
    if postgres_enabled():
        doc = dict(queued_doc(job_id), retry_count=retry_count)
        try:
            _pg_write(job_id, clip_id, doc)
        except Exception as e:  # noqa: BLE001
            print(f"[jobstore] could not record retry for {job_id}: {e}")


def forget(job_id: str, clip_id: Optional[str] = None) -> None:
    """Removal deletes the job record -- every row for the job and, given the
    clip, for the lesson. The tombstone lives on the lesson, not on the job, so
    there is nothing here worth keeping -- and a job row that outlived its
    takedown is exactly the kind of leftover the removal path exists to prevent.

    Whenever a database is configured, not only in postgres mode: rows written
    while the flag was on outlive a rollback to the Volume backend, and a
    removal must still reach them. Called by retention.delete_clip, so the
    takedown, the expiry sweep and the audit's --fix all do it."""
    if not os.environ.get("DATABASE_URL"):
        return
    try:
        with connection() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id = %s OR clip_id = %s",
                         (job_id, clip_id or job_id))
    except Exception as e:  # noqa: BLE001
        print(f"[jobstore] could not delete job row {job_id}: {e}")


def health() -> dict:
    """What /health reports. Never the connection string, never a credential --
    only whether the thing is reachable, because that is the question at 2am."""
    out = {"backend": backend(), "database_url_set": bool(os.environ.get("DATABASE_URL"))}
    if not postgres_enabled():
        return out
    try:
        with connection() as conn:
            (n,) = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()
        out["postgres"] = "ok"
        out["migrations_applied"] = n
    except Exception as e:  # noqa: BLE001
        out["postgres"] = f"unreachable: {type(e).__name__}"
    return out
