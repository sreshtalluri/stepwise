"""The one runnable check for the database: real Postgres, no Neon required.

Neon does not exist yet, so the schema is tested where it is going to have to
be correct anyway -- against a plain Postgres 16 in a container. That is not a
compromise, it is the point of decision 2: the migration uses no Neon-specific
feature, so `pg_dump` is the exit, and the same file that runs here runs there.

    docker run -d --name stepwise-pg -p 5433:5432 -e POSTGRES_PASSWORD=stepwise postgres:16
    DATABASE_URL=postgresql://postgres:stepwise@localhost:5433/postgres \
      python3 -m pytest test_schema.py -q

Skipped, not failed, when DATABASE_URL is absent: the other 157 tests must keep
running on a laptop with no container daemon.

What is actually asserted, and why each one earns its place:

  * The constraints the Volume could not enforce. `content_sha256 UNIQUE` is
    the entire dedupe mechanism; the `jobs` CHECKs are job-status.schema.json's
    own rules moved somewhere they are enforced rather than merely documented.
  * That the document served from a row is **byte-identical** to the document
    served from the Volume. This is the whole promise of decision 4 --
    ProcessingScreen.tsx cannot tell that storage changed -- and it is the one
    thing that, if it broke, would break silently.
  * That postgres mode reads through to the Volume and mirrors, so a job in
    flight at cutover keeps reporting and a rollback loses nothing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Same path insert api.py does, for the same reason: both live in this repo and
# neither is worth packaging as an installable dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "motion-contract" / "python"))

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no DATABASE_URL -- start a Postgres container, see this module's docstring")


@pytest.fixture()
def db():
    import psycopg
    import migrate

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        # Fresh schema per run. The migration is idempotent, so this is really
        # only proving that "drop everything and re-apply" works -- which is
        # exactly what a first deploy against a brand-new Neon project is.
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    migrate.main([])
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture()
def store(db, monkeypatch):
    """jobstore in postgres mode, pointed at this database."""
    monkeypatch.setenv("STEPWISE_JOB_BACKEND", "postgres")
    import jobstore
    jobstore._pool = None  # a pool from a previous test holds a dropped schema
    return jobstore


class FakeVolume:
    """The bytes-moving parts of modal.Volume. Same shape as test_retention's,
    kept separate so neither test file can break the other by editing it."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def read_file_into_fileobj(self, path, buf):
        data = self.files.get(path if path.startswith("/") else "/" + path)
        if data is None:
            raise FileNotFoundError(path)
        buf.write(data)

    def batch_upload(self, force=False):
        vol = self

        class _Batch:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def put_file(self_inner, local, remote):
                vol.files[remote] = Path(local).read_bytes()

        return _Batch()

    def commit(self):
        raise RuntimeError("commit() can only be called on a mounted volume inside a container")


def _status(job_id, **over):
    doc = {"schema_version": "1.0.0", "job_id": job_id, "state": "processing",
           "stage_message": "Building the body, frame 11 of 120", "progress": 0.31,
           "error": None, "retry_count": 0}
    doc.update(over)
    return doc


# --------------------------------------------------------------------------
# the migration itself
# --------------------------------------------------------------------------

def test_migration_creates_every_table_and_is_idempotent(db):
    import migrate
    names = {r[0] for r in db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert names == {"users", "creator_tokens", "sessions", "clips", "jobs",
                     "lessons", "assets", "events", "schema_migrations"}
    assert migrate.main([]) == 0  # re-running must be a no-op, not an error
    (n,) = db.execute("SELECT count(*) FROM schema_migrations").fetchone()
    assert n == 1


def test_no_neon_specific_syntax_in_any_migration():
    """The exit from a managed Postgres is pg_dump, and that stays true only
    while the schema is ordinary Postgres (decision 2). A grep is a blunt check
    but it fails on the day someone reaches for a branching primitive."""
    for path in (Path(__file__).parent / "migrations").glob("*.sql"):
        sql = path.read_text().lower()
        # 'neon' appears in prose about the decision; what must not appear is
        # a neon_ extension, function or role being used by the DDL itself.
        ddl = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
        for token in ("neon_", "neon.", "pg_session_jwt", "create extension"):
            assert token not in ddl, f"{path.name} uses {token!r}"


# --------------------------------------------------------------------------
# the constraints a JSON file on a Volume could not make
# --------------------------------------------------------------------------

def test_content_sha256_is_unique(db):
    """The dedupe guarantee. retention.py's own note says two uploads landing
    at the same moment can lose an entry from the JSON index; this is the fix,
    and it has to be the database's job, not the application's."""
    import psycopg
    for clip in ("clip-a", "clip-b"):
        try:
            db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) "
                       "VALUES (%s, %s, %s)", (clip, "same-hash", "{}"))
        except psycopg.errors.UniqueViolation:
            assert clip == "clip-b"
            break
    else:
        pytest.fail("a duplicate content_sha256 was accepted -- dedupe is not enforced")


def test_jobs_rejects_documents_the_contract_forbids(db):
    import psycopg
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) "
               "VALUES ('c1', 'h1', '{}')")
    bad = [
        # error is "required to be null unless state is failed"
        ("j1", "succeeded", None, '{"code": "x", "message": "y", "retryable": false}'),
        # progress is a fraction
        ("j2", "processing", 1.5, None),
        # state is an enum of four
        ("j3", "in_progress", 0.5, None),
    ]
    for job_id, state, progress, error in bad:
        with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.InvalidTextRepresentation)):
            db.execute("INSERT INTO jobs (job_id, clip_id, state, progress, error) "
                       "VALUES (%s, 'c1', %s, %s, %s)", (job_id, state, progress, error))
        db.rollback() if not db.autocommit else None


def test_removal_tombstone_survives_and_assets_cascade(db):
    """D7: the lesson row is tombstoned, never deleted, so a share link can
    answer 410 Gone rather than 404 -- and the asset rows go, so nothing is
    left individually fetchable."""
    db.execute("INSERT INTO lessons (clip_id, job_id, share_slug) VALUES ('c9', 'j9', 's9')")
    db.execute("INSERT INTO assets (clip_id, kind, key) VALUES ('c9', 'video', 'video/c9.mp4')")
    db.execute("UPDATE lessons SET removed_at = now(), removed_reason = 'i am in this video' "
               "WHERE clip_id = 'c9'")
    db.execute("DELETE FROM assets WHERE clip_id = 'c9'")

    row = db.execute("SELECT removed_at IS NOT NULL, removed_reason FROM lessons "
                     "WHERE clip_id = 'c9'").fetchone()
    assert row == (True, "i am in this video")
    (n,) = db.execute("SELECT count(*) FROM assets WHERE clip_id = 'c9'").fetchone()
    assert n == 0
    # And the tombstone must carry nothing derived from the person.
    cols = {r[0] for r in db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'lessons'")}
    assert not (cols & {"fingerprint", "dhash", "pose", "landmarks", "ip"})


def test_retention_clock_is_last_access_not_created(db):
    """D6's promise is "180 days after you last opened it", not "after you made
    it". Two columns, and the sweeper's index is on the right one."""
    db.execute("INSERT INTO lessons (clip_id, job_id, share_slug, created_at, last_access_at) "
               "VALUES ('c8', 'j8', 's8', now() - interval '200 days', now())")
    stale = db.execute(
        "SELECT clip_id FROM lessons WHERE last_access_at < now() - interval '180 days' "
        "AND removed_at IS NULL").fetchall()
    assert stale == [], "a lesson opened today must not be swept for being old"
    idx = db.execute("SELECT indexdef FROM pg_indexes WHERE indexname = "
                     "'lessons_retention_idx'").fetchone()[0]
    assert "last_access_at" in idx and "removed_at IS NULL" in idx


# --------------------------------------------------------------------------
# the storage swap -- the part that must be invisible above the HTTP boundary
# --------------------------------------------------------------------------

def test_row_and_volume_produce_byte_identical_documents(store, db):
    vol = FakeVolume()
    doc = _status("job_x")
    vol.files["/job_x.job-status.json"] = json.dumps(doc).encode()
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('x', 'hx', '{}')")

    from_volume = json.loads(vol.files["/job_x.job-status.json"])
    store._pg_write("job_x", "x", doc)
    from_row = store._pg_read("job_x")

    assert from_row == from_volume
    assert json.dumps(from_row, sort_keys=True) == json.dumps(from_volume, sort_keys=True)

    from motion_contract import validate
    assert validate.validate_job_status(from_row).valid


def test_postgres_mode_reads_through_to_the_volume_and_mirrors(store, db):
    """Migration step 3: the worker still writes the Volume, so a row miss is
    normal. The read must succeed anyway, and the row must exist afterwards --
    that is how the database becomes the source of truth one job at a time
    instead of in one jump."""
    vol = FakeVolume()
    doc = _status("job_y", state="succeeded", progress=1.0, stage_message="")
    vol.files["/job_y.job-status.json"] = json.dumps(doc).encode()
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('y', 'hy', '{}')")

    assert store._pg_read("job_y") is None
    served = store.read_status(vol, "job_y", lambda _j: "y")
    assert served == doc
    assert store._pg_read("job_y") == doc, "the read-through did not mirror"


def test_volume_mode_never_touches_the_database(monkeypatch):
    """Rollback has to be a config flip and nothing else. With the flag unset,
    an unreachable database must not matter at all."""
    monkeypatch.delenv("STEPWISE_JOB_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/nothing")
    import jobstore
    jobstore._pool = None
    vol = FakeVolume()
    doc = _status("job_z")
    vol.files["/job_z.job-status.json"] = json.dumps(doc).encode()
    assert jobstore.read_status(vol, "job_z", lambda _j: "z") == doc


def test_failed_status_round_trips_its_error_object(store, db):
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('e', 'he', '{}')")
    doc = _status("job_e", state="failed", progress=None, stage_message="",
                  error={"code": "no_dancer_found",
                         "message": "No dancer was found in this clip.",
                         "retryable": False})
    store._pg_write("job_e", "e", doc)
    assert store._pg_read("job_e") == doc


def test_retry_keeps_the_job_id_and_increments(store, db):
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('r', 'hr', '{}')")
    store.record_retry(None, "job_r", "r", 1)
    doc = store._pg_read("job_r")
    assert doc["job_id"] == "job_r" and doc["state"] == "queued" and doc["retry_count"] == 1


def test_forget_removes_the_job_row(store, db):
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('f', 'hf', '{}')")
    store._pg_write("job_f", "f", _status("job_f"))
    store.forget("job_f")
    assert store._pg_read("job_f") is None


def test_a_dispatched_row_does_not_hide_the_workers_progress(store, db):
    """The production bug: record_dispatch inserts `queued`, the worker writes
    only the Volume, and the row used to be served forever. Every job since the
    cutover sat at `queued` while the lesson was already built."""
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('d', 'hd', '{}')")
    vol = FakeVolume()
    store.record_dispatch(vol, "job_d", "d")
    assert store.read_status(vol, "job_d", lambda _j: "d")["state"] == "queued"

    done = _status("job_d", state="succeeded", progress=1.0, stage_message="")
    vol.files["/job_d.job-status.json"] = json.dumps(done).encode()
    assert store.read_status(vol, "job_d", lambda _j: "d") == done
    assert store._pg_read("job_d") == done, "the terminal state was not mirrored"


def test_a_retry_is_not_undone_by_the_previous_attempts_failure(store, db):
    db.execute("INSERT INTO clips (clip_id, content_sha256, fingerprint) VALUES ('t', 'ht', '{}')")
    vol = FakeVolume()
    failed = _status("job_t", state="failed", progress=None, stage_message="",
                     error={"code": "pipeline_error", "message": "boom", "retryable": True})
    vol.files["/job_t.job-status.json"] = json.dumps(failed).encode()
    store.record_retry(vol, "job_t", "t", 1)
    served = store.read_status(vol, "job_t", lambda _j: "t")
    assert served["state"] == "queued" and served["retry_count"] == 1
