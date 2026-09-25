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
