"""ratelimit.py against real Postgres, plus the no-database path.

The Postgres tests reuse test_schema.py's fixtures (fresh schema per test) and
skip without DATABASE_URL, exactly like it. The degrade and header tests need
nothing and always run.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi import HTTPException

import ratelimit
from test_retention import NO_REQUEST, _seed_lesson, api  # noqa: F401 -- fixtures
from test_schema import db, store  # noqa: F401 -- fixtures

needs_pg = pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                              reason="no DATABASE_URL -- see test_schema.py")


def _dispatches(db):
    return db.execute("SELECT count(*) FROM events WHERE name = 'dispatch'").fetchone()[0]


@needs_pg
def test_per_ip_hour_limit_refuses_without_recording(store, db, monkeypatch):
    monkeypatch.setenv("STEPWISE_LIMIT_IP_HOUR", "2")
    ratelimit.charge("203.0.113.7", "job_a", "a")
    ratelimit.charge("203.0.113.7", "job_b", "b")
    with pytest.raises(ratelimit.Limited) as e:
        ratelimit.charge("203.0.113.7", "job_c", "c")
    assert e.value.code == "too_many_lessons"
    assert 60 <= e.value.retry_after <= 3600
    assert _dispatches(db) == 2, "a refused request must not use up quota"

    ratelimit.charge("198.51.100.1", "job_d", "d")  # someone else is unaffected
    assert _dispatches(db) == 3

    # Hashed, never stored raw.
    dump = str(db.execute("SELECT * FROM events").fetchall())
    assert "203.0.113.7" not in dump and "198.51.100.1" not in dump


@needs_pg
def test_per_ip_day_limit(store, db, monkeypatch):
    monkeypatch.setenv("STEPWISE_LIMIT_IP_DAY", "1")
    ratelimit.charge("203.0.113.7", "job_a", "a")
    with pytest.raises(ratelimit.Limited):
        ratelimit.charge("203.0.113.7", "job_b", "b")


@needs_pg
def test_global_daily_cap_applies_across_ips(store, db, monkeypatch):
    monkeypatch.setenv("STEPWISE_LIMIT_GLOBAL_DAY", "3")
    for i in range(3):
        ratelimit.charge(f"198.51.100.{i}", f"job_{i}", str(i))
    with pytest.raises(ratelimit.Limited) as e:
        ratelimit.charge("192.0.2.99", "job_x", "x")
    assert e.value.code == "daily_limit_reached"
    assert "already made still open" in e.value.message


@needs_pg
def test_dispatches_outside_the_window_do_not_count(store, db, monkeypatch):
    monkeypatch.setenv("STEPWISE_LIMIT_IP_HOUR", "1")
    monkeypatch.setenv("STEPWISE_LIMIT_GLOBAL_DAY", "1")
    db.execute("INSERT INTO events (name, occurred_at) VALUES ('dispatch', now() - interval '25 hours')")
    ratelimit.charge("203.0.113.7", "job_a", "a")  # the old one aged out of both windows


@needs_pg
def test_dispatch_endpoint_answers_429_but_a_dedupe_hit_is_free(api, store, db, monkeypatch, tmp_path):  # noqa: F811
    """The wiring in api.py: exhausted quota is a 429 with Retry-After and the
    upload screen's error shape, and it spends nothing -- while re-opening an
    existing lesson still works, because a dedupe hit dispatches no GPU."""
    import fingerprint

    monkeypatch.setenv("STEPWISE_LIMIT_GLOBAL_DAY", "0")
    old = tmp_path / "old.mp4"
    old.write_bytes(b"already a lesson")
    _seed_lesson(api, "abc", "job_abc", fingerprint.fingerprint(str(old)))

    class _Upload:
        def __init__(self, path):
            self._f = open(path, "rb")

        async def read(self, n):
            return self._f.read(n)

    hit = asyncio.run(api.upload_clip(NO_REQUEST, _Upload(old)))
    assert hit.deduplicated and hit.clip_id == "abc"

    new = tmp_path / "new.mp4"
    new.write_bytes(b"never seen")
    with pytest.raises(HTTPException) as e:
        asyncio.run(api.upload_clip(NO_REQUEST, _Upload(new)))
    assert e.value.status_code == 429
    assert int(e.value.headers["Retry-After"]) >= 60
    assert e.value.detail["error"]["code"] == "daily_limit_reached"
    assert e.value.detail["error"]["retryable"] is True
    assert api._spawned == [] and set(api.uploads_volume.files) == {"/abc.mp4"}


def test_no_postgres_means_allow_and_say_so_once(monkeypatch, capsys):
    monkeypatch.delenv("STEPWISE_JOB_BACKEND", raising=False)
    monkeypatch.setattr(ratelimit, "_warned", False)
    monkeypatch.setattr(ratelimit.jobstore, "connection",
                        lambda: pytest.fail("the volume backend must not touch a database"))
    for _ in range(3):
        ratelimit.charge("203.0.113.7", "job_a", "a")
    assert capsys.readouterr().out.count("limits are OFF") == 1


def test_client_ip_prefers_cloudflare_then_the_socket():
    assert ratelimit.client_ip({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"}, "3.3.3.3") == "1.1.1.1"
    assert ratelimit.client_ip({"x-forwarded-for": "2.2.2.2, 10.0.0.1"}, "3.3.3.3") == "3.3.3.3"
    assert ratelimit.client_ip({"x-forwarded-for": "2.2.2.2, 10.0.0.1"}, None) == "2.2.2.2"
    assert ratelimit.client_ip({}, None) == "unknown"
