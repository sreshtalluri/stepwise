"""The beat proposal's trip from W11's dataclass into the frozen contract.

One thing is worth a test here and it is not the beat tracking (W11 owns that,
and it needs audio): it is that the grid this service writes agrees with the
grid the contract validates. Two copies of one formula, in two languages, in two
packages -- `motion_result._proposed_counts` and the validator's invariant --
and the number they disagree about would be a count strip that runs one count
past the end of the dance with nothing anywhere saying why.

    python -m pytest services/motion-api/test_proposed_counts.py
"""
import sys
from pathlib import Path

import pytest

from motion_result import _proposed_counts

_CONTRACT_PY = Path(__file__).resolve().parents[2] / "packages" / "motion-contract" / "python"


def _grid(**over):
    """`beat_detect.propose_grid()`'s output shape, as asdict() produces it."""
    base = {
        "count_one_s": 0.4,
        "seconds_per_count": 0.5,
        # None is what propose_grid returns when no clip_duration_s was passed,
        # which is exactly how this service calls it -- the value below is
        # ignored and re-derived from the sample timeline.
        "count_total": None,
        "confidence": 0.93,
        "bpm": 120.0,
        "alternates": [
            {"label": "double-time", "seconds_per_count": 0.25, "bpm": 240.0},
            {"label": "half-time", "seconds_per_count": 1.0, "bpm": 60.0},
        ],
        "warnings": ["tempo is outside the typical range"],
    }
    base.update(over)
    return base


def _timeline(n=210, fps=15):
    return [round(i / fps, 6) for i in range(n)]


def test_no_proposal_is_a_normal_outcome():
    assert _proposed_counts(None, _timeline()) is None
    assert _proposed_counts(_grid(), []) is None
    assert _proposed_counts(_grid(seconds_per_count=0.0), _timeline()) is None


def test_confidence_alternates_and_warnings_all_survive_the_trip():
    # The honesty rule only has teeth if the doubt arrives with the grid.
    out = _proposed_counts(_grid(), _timeline())
    assert out["confidence"] == 0.93
    assert out["bpm"] == 120.0
    assert [a["label"] for a in out["alternates"]] == ["double-time", "half-time"]
    assert out["warnings"] == ["tempo is outside the typical range"]


def test_count_total_is_sized_against_the_sample_timeline_not_the_container():
    times = _timeline()  # 210 samples at 15 fps -> last slot at 13.933333s
    out = _proposed_counts(_grid(), times)
    # 14.0s (the container duration a beat tracker would have seen) would give
    # 28 counts too here, but the boundary case below is what separates them.
    assert out["count_total"] == 28
    # Count 1 lands on the anchor, and the last count starts inside the clip.
    assert out["count_one_s"] + (out["count_total"] - 1) * out["seconds_per_count"] <= times[-1]
    assert out["count_one_s"] + out["count_total"] * out["seconds_per_count"] > times[-1]


@pytest.mark.skipif(not _CONTRACT_PY.exists(), reason="motion-contract python package not present")
def test_the_contract_validator_agrees_with_the_number_this_service_writes():
    sys.path.insert(0, str(_CONTRACT_PY))
    from motion_contract.validate import _check_invariants

    # Deliberately awkward numbers: an anchor that is not on a sample boundary
    # and a tempo that does not divide the clip evenly is where two independent
    # floor() implementations drift apart if they ever will.
    times = _timeline(n=89, fps=15)
    grid = _grid(count_one_s=0.21, seconds_per_count=60.0 / 196.0, bpm=196.0)
    out = _proposed_counts(grid, times)

    doc = {"sample_times_s": times, "joint_hierarchy": {"joints": []}, "persons": [],
           "grounding": {"status": "none", "floor_plane": None}, "proposed_counts": out}
    assert _check_invariants(doc) == [], "the service and the contract disagree about count_total"

    doc["proposed_counts"] = dict(out, count_total=out["count_total"] + 1)
    assert _check_invariants(doc), "the invariant does not actually catch an off-by-one grid"


@pytest.mark.skipif(not _CONTRACT_PY.exists(), reason="motion-contract python package not present")
def test_count_one_alternates_survive_and_match_the_schema():
    # "Try another 1" only works if the candidates reach the viewer; one past
    # the end of the clip is dropped rather than offered.
    import json

    import jsonschema

    times = _timeline()
    alts = [
        {"count_one_s": 1.4, "shift_counts": 2, "confidence": 0.33},
        {"count_one_s": 0.0, "shift_counts": -1, "confidence": 0.22},
        {"count_one_s": 99.0, "shift_counts": 1, "confidence": 0.2},
    ]
    out = _proposed_counts(_grid(count_one_alternates=alts), times)
    assert [a["shift_counts"] for a in out["count_one_alternates"]] == [2, -1]
    assert "count_one_alternates" not in _proposed_counts(_grid(), times)  # older producers

    schema = json.loads((_CONTRACT_PY.parent / "schema" / "motion-result.schema.json").read_text())
    jsonschema.validate(out, {"$defs": schema["$defs"], **schema["$defs"]["ProposedCounts"]})


@pytest.mark.skipif(not _CONTRACT_PY.exists(), reason="motion-contract python package not present")
def test_count_one_confidence_is_passed_through_and_matches_the_schema():
    # The phase confidence (which beat is 1) rides beside the grid confidence;
    # beats written before it existed carry none, and none is invented.
    import json

    import jsonschema

    out = _proposed_counts(_grid(count_one_confidence=0.14), _timeline())
    assert out["count_one_confidence"] == 0.14
    assert "count_one_confidence" not in _proposed_counts(_grid(), _timeline())

    schema = json.loads((_CONTRACT_PY.parent / "schema" / "motion-result.schema.json").read_text())
    jsonschema.validate(out, {"$defs": schema["$defs"], **schema["$defs"]["ProposedCounts"]})
