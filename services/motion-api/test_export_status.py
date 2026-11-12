"""export_clip_gltf owns a job's terminal status now that run_clip spawns it
and returns (docs/research/pipeline-latency.md #1). The order is the contract:
files committed -> R2 published -> "succeeded". A failure is a retryable
`export_error`. A standalone re-export touches no job status at all.

Runs the real wrapper with the pymomentum-heavy body swapped for a recorder;
importing modal_app needs the `modal` package but no token and no network
beyond Secret lookups that degrade to "not configured".
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import modal_app  # noqa: E402

export = modal_app._export_and_report


@pytest.fixture()
def removed(monkeypatch):
    """The clip_ids whose tombstone exists -- no Volume, no Modal token."""
    import retention  # whichever copy is live: test_retention re-imports it
    gone: set = set()
    monkeypatch.setattr(retention, "is_removed", lambda vol, clip_id, reload=False: clip_id in gone)
    return gone


@pytest.fixture()
def events(monkeypatch, removed):
    import retention
    log: list = []

    def body(clip_id, job_id=None):
        log.append("files committed")   # _export_clip_gltf: results.commit() ...
        log.append("r2 published")      # ... then _publish_to_r2, then returns
        if clip_id == "boom":
            raise RuntimeError("pymomentum fell over")
        if clip_id == "removed-meanwhile":
            removed.add(clip_id)          # a takedown landed while export ran
        return {"clip_id": clip_id}

    def status(job_id, state, msg, progress, retry_count, error=None, milestones=None, clip_id=None):
        retention.ensure_not_removed(None, clip_id)  # the real one refuses too
        log.append((state, progress, retry_count, error and error["code"], error and error["retryable"]))

    monkeypatch.setattr(modal_app, "_export_clip_gltf", body)
    monkeypatch.setattr(modal_app, "_write_job_status", status)
    monkeypatch.setattr(modal_app, "_prune_old_versions", lambda clip_id, out: log.append("pruned"))
    monkeypatch.setattr(retention, "stop_and_sweep",
                        lambda up, res, clip_id, job_id, mounts=None:
                        log.append(("swept", clip_id)) or {"clip_id": clip_id, "removed": True})
    return log


def test_succeeded_is_written_only_after_files_and_r2(events):
    assert export("c1", "job_c1", 1) == {"clip_id": "c1"}
    assert events == ["files committed", "r2 published", ("succeeded", 1.0, 1, None, None), "pruned"]


def test_export_failure_is_a_retryable_export_error(events):
    with pytest.raises(RuntimeError):
        export("boom", "job_boom", 0)
    assert events[-1] == ("failed", None, 0, "export_error", True)
    assert ("succeeded", 1.0, 0, None, None) not in events


def test_standalone_reexport_leaves_job_status_alone(events):
    export("c1", "job_c1", None)
    assert events == ["files committed", "r2 published", "pruned"]


def test_a_removed_lesson_is_never_exported(events, removed):
    removed.add("c1")
    assert export("c1", "job_c1", 0)["removed"] is True
    assert events == [("swept", "c1")], "no work, no status -- only the sweep"


def test_removal_during_export_stops_without_a_failed_status(events):
    """job_6037: the tombstone is the only record -- no `failed`, no
    `succeeded` -- and what export had already written is swept."""
    assert export("removed-meanwhile", "job_r", 0)["removed"] is True
    assert events == ["files committed", "r2 published", ("swept", "removed-meanwhile")]


# ---- _publish_to_r2: everything immutable together, the "latest" copy last ----

@pytest.fixture
def r2(monkeypatch):
    """A recording stand-in for storage: each put takes a moment, so an
    out-of-order "latest" write would show."""
    import threading
    import time

    import retention
    import storage
    puts, lock = [], threading.Lock()

    def put_file(key, path, content_type, **kwargs):
        if "boom" in key:
            raise RuntimeError("r2 blip")
        time.sleep(0.05)
        with lock:
            puts.append(key)
        return key

    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "client", lambda: None)
    monkeypatch.setattr(storage, "put_file", put_file)
    monkeypatch.setattr(retention, "ensure_not_removed", lambda vol, clip_id: None)
    return puts


def test_publish_writes_the_latest_copy_after_everything_it_points_at(r2):
    import time

    import storage
    t0 = time.perf_counter()
    written = modal_app._publish_to_r2("c", ["/x/c.t1.glb", "/x/c.t2.glb", "/x/c.t3.glb"], "job_c", "abc123")
    took = time.perf_counter() - t0
    latest = storage.motion_result_key("c")
    assert r2[-1] == latest and written[-1] == latest
    assert set(r2[:-1]) == {storage.glb_key("c.t1.glb"), storage.glb_key("c.t2.glb"),
                            storage.glb_key("c.t3.glb"), storage.motion_result_key("c", "abc123")}
    assert took < 0.2, "four 50 ms puts in parallel, then one: not five in a row (0.25 s)"


def test_publish_never_points_latest_at_a_version_that_failed_to_upload(r2):
    import storage
    written = modal_app._publish_to_r2("c", ["/x/c.t1.glb", "/x/boom.glb"], "job_c", "abc123")
    assert storage.motion_result_key("c") not in r2
    assert set(written) == {storage.glb_key("c.t1.glb"), storage.motion_result_key("c", "abc123")}


def test_stage_marks_join_the_ones_run_clip_wrote(monkeypatch, tmp_path):
    import json
    monkeypatch.setattr(modal_app, "RESULTS_DIR", str(tmp_path))
    modal_app._mark_stages("nofile", finished=5.0)  # nothing to add to: not created
    assert not (tmp_path / "nofile.performance.json").exists()
    (tmp_path / "c.performance.json").write_text(json.dumps({"fps": 3.1, "stage_at": {"started": 1.0}}))
    modal_app._mark_stages("c", export_started=2.004, finished=3.0)
    assert json.loads((tmp_path / "c.performance.json").read_text()) == {
        "fps": 3.1, "stage_at": {"started": 1.0, "export_started": 2.0, "finished": 3.0}}
