"""The export watchdog (api._fail_dead_export): a job whose export container
died without raising -- OOM, its Modal timeout, a crash -- must end `failed`
with a retryable `export_error`, not sit at "Building the 3D body file"
forever. Runs the real handlers against test_retention's in-memory Volume and
hand-off Dict, with modal.FunctionCall answering the way the real client was
measured to (api.py, "Export watchdog").

    python3 -m pytest test_export_watchdog.py -q
"""
from __future__ import annotations

import json
import re
import time
import types
from pathlib import Path

import pytest

from test_retention import NO_REQUEST, _removal, _seed_lesson, api  # noqa: F401 -- the fixture

JOB, CLIP = "job_abc", "abc"


class InternalFailure(Exception):
    """Stands in for modal.exception.InternalFailure ("Server has lost track of input")."""


@pytest.fixture()
def modal_calls(api, monkeypatch):  # noqa: F811
    """What each export call does when asked: 'dead', 'running' or 'returned'.
    Records every call id Modal was asked about."""
    state: dict[str, str] = {}
    asked: list[str] = []
    cancelled: list[str] = []

    def get(call_id, timeout=None):
        asked.append(call_id)
        if state[call_id] == "dead":
            raise InternalFailure("Server has lost track of input")
        if state[call_id] == "running":
            raise TimeoutError()
        return {"clip_id": CLIP}

    monkeypatch.setattr(api.modal, "FunctionCall", types.SimpleNamespace(
        from_id=lambda call_id: types.SimpleNamespace(get=lambda timeout=None: get(call_id, timeout),
                                                      cancel=lambda: cancelled.append(call_id))),
        raising=False)
    monkeypatch.setattr(api.modal, "exception",
                        types.SimpleNamespace(ConnectionError=type("CE", (Exception,), {})), raising=False)
    state["asked"], state["cancelled"] = asked, cancelled  # type: ignore[assignment]
    return state


def _at_export(api, retry_count=0, export="fc-export", age_s=800.0, record_retry=None):  # noqa: F811
    """A job exactly as run_clip leaves it: its last status written, export
    spawned `age_s` ago and recorded in the hand-off Dict."""
    api.results_volume.files[f"/{JOB}.job-meta.json"] = json.dumps({"clip_id": CLIP}).encode()
    api.results_volume.files[f"/{JOB}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": JOB, "state": "processing",
        "stage_message": "Building the 3D body file", "progress": 0.97, "error": None,
        "retry_count": retry_count}).encode()
    if export:
        api._handoff_dict[f"calls:{JOB}"] = {
            "gpu": "fc-run", "beats": None, "token": None, "export": export,
            "export_at": time.time() - age_s,
            "retry_count": retry_count if record_retry is None else record_retry}


def _volume_status(api):  # noqa: F811
    return json.loads(api.results_volume.files[f"/{JOB}.job-status.json"])


def test_a_dead_export_becomes_a_retryable_export_error_and_retry_reruns_it(api, modal_calls):  # noqa: F811
    _at_export(api)
    modal_calls["fc-export"] = "dead"
    doc = api.get_job_status(JOB)
    assert doc["state"] == "failed" and doc["progress"] is None
    assert doc["error"]["code"] == "export_error" and doc["error"]["retryable"] is True
    assert _volume_status(api) == doc, "not written where export would have written it"
    assert api.get_job_status(JOB) == doc, "idempotent: the next poll reads the same failure"

    assert api.retry_job(JOB, NO_REQUEST) == {"job_id": JOB, "retry_count": 1}
    assert api._spawned[-1] == {"clip_id": CLIP, "job_id": JOB, "retry_count": 1}


def test_an_overdue_export_that_is_still_running_is_left_alone(api, modal_calls):  # noqa: F811
    _at_export(api)
    modal_calls["fc-export"] = "running"   # queued for a CPU, or on a restart
    assert api.get_job_status(JOB)["state"] == "processing"
    assert modal_calls["asked"] == ["fc-export"]
    assert api.get_job_status(JOB)["state"] == "processing"
    assert modal_calls["asked"] == ["fc-export"], "asked Modal again inside the recheck window"


def test_an_export_still_running_long_past_its_timeout_is_given_up_on(api, modal_calls):  # noqa: F811
    """os._exit in a container: Modal restarts it and keeps calling the input
    running (measured, well past the function's timeout)."""
    _at_export(api, age_s=api.EXPORT_GIVE_UP_S + 1)
    modal_calls["fc-export"] = "running"
    assert api.get_job_status(JOB)["error"]["code"] == "export_error"
    assert modal_calls["cancelled"] == ["fc-export"], "a given-up call must be stopped first"


def test_an_export_that_returned_is_not_failed(api, modal_calls):  # noqa: F811
    """Its `succeeded` is on the Volume; this replica just has not seen it yet."""
    _at_export(api)
    modal_calls["fc-export"] = "returned"
    assert api.get_job_status(JOB)["state"] == "processing"


def test_a_fresh_export_costs_no_modal_call(api, modal_calls, monkeypatch):  # noqa: F811
    _at_export(api, age_s=30)
    reads = []
    real_get = api._handoff_dict.get
    monkeypatch.setattr(api._handoff_dict, "get", lambda *a: reads.append(a) or real_get(*a), raising=False)
    for _ in range(5):
        assert api.get_job_status(JOB)["state"] == "processing"
    assert modal_calls["asked"] == [] and len(reads) == 1, "the fast path must stay a dict lookup"


def test_a_succeeded_written_meanwhile_wins(api, modal_calls, monkeypatch):  # noqa: F811
    _at_export(api)
    modal_calls["fc-export"] = "dead"
    real = api._export_call_dead

    def export_finished_first(call_id):
        dead = real(call_id)
        api.results_volume.files[f"/{JOB}.job-status.json"] = json.dumps({
            "schema_version": "1.0.0", "job_id": JOB, "state": "succeeded",
            "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0}).encode()
        return dead

    monkeypatch.setattr(api, "_export_call_dead", export_finished_first)
    monkeypatch.setattr(api, "_prime_result", lambda job_id: None)
    assert api.get_job_status(JOB)["state"] == "succeeded"
    assert _volume_status(api)["state"] == "succeeded"


def test_a_removed_lesson_stays_410(api, modal_calls):  # noqa: F811
    from fastapi import HTTPException
    _seed_lesson(api, CLIP, JOB)
    api.remove_lesson(CLIP, _removal(api), NO_REQUEST)
    _at_export(api)                        # the worker's last write landed after the removal
    modal_calls["fc-export"] = "dead"      # export stopped at its tombstone check
    with pytest.raises(HTTPException) as e:
        api.get_job_status(JOB)
    assert e.value.status_code == 410
    assert _volume_status(api)["state"] == "processing", "a removed lesson became a retryable failure"


def test_no_recorded_call_fails_on_time_alone(api, modal_calls, monkeypatch):  # noqa: F811
    """A failed Dict put, or a GPU that died between the status write and the
    spawn: the clock starts when this replica first sees the job there."""
    _at_export(api, export=None)
    assert api.get_job_status(JOB)["state"] == "processing"
    later = time.time() + api.EXPORT_STALE_S + 1
    monkeypatch.setattr(api, "time", types.SimpleNamespace(time=lambda: later, monotonic=time.monotonic))
    assert api.get_job_status(JOB)["error"]["code"] == "export_error"
    assert modal_calls["asked"] == []


def test_a_previous_attempts_export_is_not_this_attempts(api, modal_calls):  # noqa: F811
    """After a retry the Dict can still name attempt 0's dead export."""
    _at_export(api, retry_count=1, record_retry=0)
    modal_calls["fc-export"] = "dead"
    assert api.get_job_status(JOB)["state"] == "processing"
    assert modal_calls["asked"] == []


def test_the_watchdog_matches_the_worker(api):  # noqa: F811
    src = (Path(__file__).resolve().parent / "modal_app.py").read_text()
    api_mod = api
    assert f'"processing", "{api_mod.EXPORT_STAGE}", 0.97' in src
    timeout = int(re.search(r"^EXPORT_TIMEOUT_S = (\d+)", src, re.M).group(1))
    assert "timeout=EXPORT_TIMEOUT_S)\ndef export_clip_gltf" in src
    assert api_mod.EXPORT_STALE_S > timeout
