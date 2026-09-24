"""Early milestones: the detections sidecar, the counts milestone, and the API
wiring that spawns counts at dispatch and serves both while the job runs.

    python -m pytest services/motion-api/test_milestones.py
"""
import json

import pytest
from fastapi import HTTPException

from milestones import build_detections, counts_milestone
from test_retention import NO_REQUEST, api  # noqa: F401 -- the api fixture

GRID = {"bpm": 117.123, "count_one_s": 0.51234, "seconds_per_count": 0.5128,
        "confidence": 0.8, "alternates": [], "warnings": [], "count_total": None}


def test_dispatch_spawns_counts_beside_run_clip_and_hands_over_the_call(api, tmp_path):
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"video")
    api._store_and_dispatch(str(clip), "abc", {}, NO_REQUEST)
    assert api._spawned == [{"clip_id": "abc", "job_id": "job_abc",
                             "beats_call_id": "fc-propose_counts"}]


def test_queued_job_shows_counts_as_soon_as_the_proposal_lands(api):
    r = api.results_volume.files
    r["/job_abc.job-meta.json"] = json.dumps({"clip_id": "abc"}).encode()
    assert "milestones" not in api.get_job_status("job_abc")

    r["/abc.beats.json"] = json.dumps(GRID).encode()
    doc = api.get_job_status("job_abc")
    assert doc["state"] == "queued"
    assert doc["milestones"]["counts"]["bpm"] == 117.12

    # A finished job carries none: the MotionResult supersedes it.
    r["/job_abc.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": "job_abc", "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0}).encode()
    assert "milestones" not in api.get_job_status("job_abc")


def test_detections_404_then_served_then_gone_after_removal(api):
    r = api.results_volume.files
    r["/job_abc.job-meta.json"] = json.dumps({"clip_id": "abc"}).encode()
    with pytest.raises(HTTPException) as e:
        api.get_job_detections("job_abc")
    assert e.value.status_code == 404

    r["/abc.detections.json"] = b'{"dancers":[]}'
    assert api.get_job_detections("job_abc").body == b'{"dancers":[]}'

    api.remove_lesson("abc", None)
    assert "/abc.detections.json" not in r
    with pytest.raises(HTTPException) as e:
        api.get_job_detections("job_abc")
    assert e.value.status_code == 410


def _det(ids, x=100.0, score=0.9):
    return {"track_ids": list(ids),
            "keypoints": [[[x, 200.0, score]] * 17 for _ in ids]}


def test_subsamples_normalises_and_drops_unconfident():
    times = [i / 15 for i in range(30)]           # 2 s at 15 fps
    raw = [_det([1, 9]) if i % 2 else _det([1]) for i in range(30)]
    doc = build_detections(times, raw, {1}, 400, 800)

    assert doc["fps"] == 5.0
    assert len(doc["times"]) == 10                # every 3rd frame
    assert [d["id"] for d in doc["dancers"]] == [1]   # track 9 never became confident
    assert doc["dancers"][0]["points"][0][0] == [0.25, 0.25]


def test_absent_dancer_and_low_score_keypoint_are_null():
    raw = [_det([]), _det([2], score=0.1)]
    doc = build_detections([0.0, 0.2], raw, [2], 100, 100)
    frames = doc["dancers"][0]["points"]
    assert frames[0] is None
    assert frames[1][0] is None


def test_counts_milestone_trims_the_grid_and_refuses_a_degenerate_one():
    assert counts_milestone(GRID) == {"bpm": 117.12, "count_one_s": 0.5123,
                                      "seconds_per_count": 0.5128, "confidence": 0.8}
    assert counts_milestone(None) is None
    assert counts_milestone(dict(GRID, seconds_per_count=0)) is None
