"""analytics.py: the allowlist and day_hash (always run), and the event log,
metrics and 13-month roll-up against real Postgres (skipped without
DATABASE_URL, like test_schema.py)."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import types

import pytest
from fastapi import HTTPException

import analytics
from test_retention import api  # noqa: F401 -- fixture
from test_schema import db, store  # noqa: F401 -- fixtures

needs_pg = pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                              reason="no DATABASE_URL -- see test_schema.py")
UA = {"user-agent": "Mozilla/5.0 test"}


def _body(*events) -> bytes:
    return json.dumps(list(events)).encode()


# --------------------------------------------------------------------------
# pure
# --------------------------------------------------------------------------

def test_allowlist_keeps_known_props_and_drops_the_rest():
    ok = analytics.validate({"name": "loop_created", "lesson": "job_abc",
                             "props": {"counts": 4, "start": 9, "snapped": True, "via": "drag",
                                       "x": 1, "url": "https://example.com/?q=me"}})
    assert ok == ("loop_created", {"counts": 4.0, "start": 9.0, "snapped": True, "via": "drag"}, "job_abc")
    for bad in [
        {"name": "pageview"},                                               # not on the list
        {"name": "loop_created", "props": {"via": "mouse"}},                # not an allowed value
        {"name": "speed_changed", "props": {"speed": "fast"}},              # wrong type
        {"name": "play_seconds", "props": {"seconds": 31}},                 # over the bucket
        {"name": "build_up_toggled", "props": {"on": 1}},                   # 1 is not a bool
        {"name": "lesson_opened", "props": {"ref": "evil.com/path?x=1"}},   # host only
        "lesson_opened",
    ]:
        assert analytics.validate(bad) is None, bad
    # A lesson id that is not an id is dropped, the event kept.
    assert analytics.validate({"name": "tap_on_one", "lesson": "../x y"}) == ("tap_on_one", {}, None)


def test_day_hash_depends_on_salt_ip_and_user_agent():
    a = analytics.day_hash(b"s1", "203.0.113.7", "UA")
    assert a == analytics.day_hash(b"s1", "203.0.113.7", "UA")
    assert a != analytics.day_hash(b"s2", "203.0.113.7", "UA"), "a new day's salt unlinks"
    assert a != analytics.day_hash(b"s1", "203.0.113.7", "UA2")
    assert b"203.0.113.7" not in a


def test_without_postgres_everything_is_dropped_and_nothing_raises(monkeypatch):
    monkeypatch.delenv("STEPWISE_JOB_BACKEND", raising=False)
    assert analytics.ingest(_body({"name": "tap_on_one"}), UA, "1.2.3.4") == 0
    analytics.record("job_created", {}, UA, None)
    analytics.record_finished({"job_id": "j", "state": "failed", "retry_count": 0}, "c", lambda: 1)


def test_database_errors_are_dropped_not_raised(monkeypatch):
    monkeypatch.setenv("STEPWISE_JOB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(analytics.jobstore, "connection", lambda: (_ for _ in ()).throw(OSError("down")))
    assert analytics.ingest(_body({"name": "tap_on_one"}), UA, "1.2.3.4") == 0


def test_garbage_bodies_are_zero_not_errors():
    for body in [b"", b"{", b'{"name":"tap_on_one"}', b"x" * (analytics.MAX_BODY + 1)]:
        assert analytics.ingest(body, UA, None) == 0


def test_admin_key_by_header_or_basic_auth(monkeypatch):
    monkeypatch.delenv("STEPWISE_ADMIN_KEY", raising=False)
    assert not analytics.admin_ok({"x-stepwise-admin-key": ""}), "unset means nobody"
    monkeypatch.setenv("STEPWISE_ADMIN_KEY", "k3y")
    assert analytics.admin_ok({"x-stepwise-admin-key": "k3y"})
    assert not analytics.admin_ok({"x-stepwise-admin-key": "nope"})
    basic = "Basic " + base64.b64encode(b"owner:k3y").decode()
    assert analytics.admin_ok({"authorization": basic})


def test_metrics_endpoint_is_404_without_the_key(api, monkeypatch):  # noqa: F811
    monkeypatch.setenv("STEPWISE_ADMIN_KEY", "k3y")
    with pytest.raises(HTTPException) as e:
        api.get_metrics(types.SimpleNamespace(headers={}))
    assert e.value.status_code == 404


def test_events_endpoint_answers_without_a_database(api, monkeypatch):  # noqa: F811
    monkeypatch.delenv("STEPWISE_JOB_BACKEND", raising=False)

    async def body():
        return _body({"name": "tap_on_one"})
    req = types.SimpleNamespace(headers=UA, client=None, body=body)
    assert asyncio.run(api.post_events(req)) == {"accepted": 0}


# --------------------------------------------------------------------------
# postgres
# --------------------------------------------------------------------------

@pytest.fixture()
def pg(store, db):  # noqa: F811
    analytics._salt = None
    analytics._FINISHED.clear()
    return db


@needs_pg
def test_batch_is_stored_hashed_with_no_ip(pg):
    n = analytics.ingest(_body({"name": "lesson_opened", "lesson": "job_1", "props": {"ref": "tiktok.com"}},
                               {"name": "speed_changed", "props": {"speed": 0.5}},
                               {"name": "nope"}), UA, "203.0.113.7")
    assert n == 2
    analytics.ingest(_body({"name": "tap_on_one", "lesson": "job_1"}), UA, "203.0.113.7")
    analytics.ingest(_body({"name": "tap_on_one"}), {"user-agent": "other"}, "203.0.113.7")
    rows = pg.execute("SELECT name, job_id, day_hash FROM events ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["lesson_opened", "speed_changed", "tap_on_one", "tap_on_one"]
    assert rows[0][2] == rows[2][2], "same visitor, same day -> same hash"
    assert rows[3][2] != rows[0][2], "another browser -> another hash"
    assert "203.0.113.7" not in str(pg.execute("SELECT * FROM events").fetchall())


@needs_pg
def test_old_salts_are_deleted(pg):
    pg.execute("INSERT INTO analytics_salts VALUES (current_date - 2, 'old')")
    analytics.ingest(_body({"name": "tap_on_one"}), UA, "1.1.1.1")
    days = [r[0] for r in pg.execute("SELECT day FROM analytics_salts")]
    assert days == [analytics._today()]


@needs_pg
def test_per_visitor_daily_cap(pg, monkeypatch):
    monkeypatch.setenv("STEPWISE_EVENTS_PER_DAY", "3")
    assert analytics.ingest(_body(*[{"name": "tap_on_one"}] * 5), UA, "1.1.1.1") == 3
    assert analytics.ingest(_body({"name": "tap_on_one"}), UA, "1.1.1.1") == 0
    assert analytics.ingest(_body({"name": "tap_on_one"}), UA, "2.2.2.2") == 1


@needs_pg
def test_job_finished_is_recorded_once_per_attempt(pg):
    pg.execute("INSERT INTO events (name, job_id, occurred_at) VALUES ('dispatch', 'job_a', now() - interval '90 seconds')")
    doc = {"job_id": "job_a", "state": "failed", "retry_count": 0,
           "error": {"code": "export_error", "message": "x", "retryable": True}}
    analytics.record_finished(doc, "a", lambda: 1 / 0)
    analytics._FINISHED.clear()  # another replica
    analytics.record_finished(doc, "a", lambda: 1 / 0)
    analytics.record_finished(dict(doc, state="succeeded", error=None, retry_count=1), "a", lambda: 2)
    rows = [r[0] for r in pg.execute("SELECT props FROM events WHERE name = 'job_finished' ORDER BY id")]
    assert len(rows) == 2
    assert rows[0]["error_code"] == "export_error" and 85 <= rows[0]["wall_s"] <= 120
    assert rows[1]["persons"] == 2 and rows[1]["state"] == "succeeded"


@needs_pg
def test_job_created_on_upload(api, pg, tmp_path):  # noqa: F811
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not really a video")
    req = types.SimpleNamespace(headers=UA, client=None)
    api._store_and_dispatch(str(video), "c1", {"duration_s": 12.34}, req)
    (props,) = pg.execute("SELECT props FROM events WHERE name = 'job_created'").fetchone()
    assert props == {"source": "file", "deduplicated": False, "seconds": 12.3}


@needs_pg
def test_metrics(pg):
    def ev(name, props=None, job=None, who=b"v1"):
        pg.execute("INSERT INTO events (name, job_id, day_hash, props) VALUES (%s, %s, %s, %s)",
                   (name, job, who, json.dumps(props or {})))
    ev("lesson_opened", {"ref": ""}, "j1")
    ev("lesson_opened", {"ref": "tiktok.com"}, "j2", b"v2")
    ev("count_one_nudged", {"by": 1}, "j1")
    for s in (30, 30, 10):
        ev("play_seconds", {"seconds": s}, "j1")
    ev("play_seconds", {"seconds": 20}, "j2", b"v2")
    ev("loop_created", {"counts": 4, "snapped": True, "via": "drag"}, "j1")
    ev("job_created", {"source": "file", "deduplicated": False}, "j1", None)
    ev("job_finished", {"state": "succeeded"}, "j1", None)
    ev("job_finished", {"state": "failed", "error_code": "too_many_dancers"}, "j3", None)
    ev("dispatch", None, "j1", b"ratelimit-hash")  # not a visitor

    m = analytics.metrics(pg, 30)
    assert m["daily"][0]["visitors"] == 2 and m["daily"][0]["uploads"] == 1
    assert m["completion_rate"] == 0.5
    assert m["top_failures"] == [{"code": "too_many_dancers", "n": 1}]
    assert m["count_one_correction_rate"] == 0.5
    assert m["median_play_seconds"] == 45  # (70, 20)
    assert {"host": "tiktok.com", "n": 1} in m["referrers"]
    assert m["loops"][0]["median_counts"] == 4


@needs_pg
def test_rollup_folds_old_days_and_keeps_recent_rows(pg):
    old = "now() - interval '14 months'"
    for who in (b"a", b"a", b"b"):
        pg.execute(f"INSERT INTO events (name, day_hash, occurred_at, props) VALUES "
                   f"('play_seconds', %s, {old}, '{{\"seconds\": 30}}')", (who,))
    pg.execute(f"INSERT INTO events (name, occurred_at, props) VALUES ('job_finished', {old}, "
               "'{\"state\": \"failed\", \"error_code\": \"export_error\"}')")
    pg.execute("INSERT INTO events (name) VALUES ('tap_on_one')")
    assert analytics.rollup(pg, dry_run=True)["rolled_up_rows"] == 4
    assert pg.execute("SELECT count(*) FROM event_daily").fetchone()[0] == 0

    assert analytics.rollup(pg)["rolled_up_rows"] == 4
    assert [r[0] for r in pg.execute("SELECT name FROM events")] == ["tap_on_one"]
    daily = {(r[0], r[1]): r[2:] for r in pg.execute("SELECT name, detail, n, visitors, seconds FROM event_daily")}
    assert daily[("play_seconds", "")] == (3, 2, 90)
    assert daily[("job_finished", "failed:export_error")][0] == 1
    assert analytics.rollup(pg)["rolled_up_rows"] == 0  # idempotent
