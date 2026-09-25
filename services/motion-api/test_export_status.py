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
def events(monkeypatch):
    log: list = []

    def body(clip_id, job_id=None):
        log.append("files committed")   # _export_clip_gltf: results.commit() ...
        log.append("r2 published")      # ... then _publish_to_r2, then returns
        if clip_id == "boom":
            raise RuntimeError("pymomentum fell over")
        return {"clip_id": clip_id}

    monkeypatch.setattr(modal_app, "_export_clip_gltf", body)
    monkeypatch.setattr(modal_app, "_write_job_status",
                        lambda job_id, state, msg, progress, retry_count, error=None, milestones=None:
                        log.append((state, progress, retry_count, error and error["code"],
                                    error and error["retryable"])))
    return log


def test_succeeded_is_written_only_after_files_and_r2(events):
    assert export("c1", "job_c1", 1) == {"clip_id": "c1"}
    assert events == ["files committed", "r2 published", ("succeeded", 1.0, 1, None, None)]


def test_export_failure_is_a_retryable_export_error(events):
    with pytest.raises(RuntimeError):
        export("boom", "job_boom", 0)
    assert events[-1] == ("failed", None, 0, "export_error", True)
    assert ("succeeded", 1.0, 0, None, None) not in events


def test_standalone_reexport_leaves_job_status_alone(events):
    export("c1", "job_c1", None)
    assert events == ["files committed", "r2 published"]
