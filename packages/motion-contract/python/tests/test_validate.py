import copy
import json
from pathlib import Path

import pytest

from motion_contract.validate import validate_job_status, validate_motion_result

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def good_lesson() -> dict:
    return load_fixture("good-lesson.json")


@pytest.fixture
def failure_lesson() -> dict:
    return load_fixture("failure-lesson.json")


def test_good_lesson_is_valid(good_lesson):
    result = validate_motion_result(good_lesson)
    assert result.errors == []
    assert result.valid is True


def test_failure_lesson_is_valid(failure_lesson):
    result = validate_motion_result(failure_lesson)
    assert result.errors == []
    assert result.valid is True


def test_failure_lesson_exercises_observed_interpolated_suppressed_simultaneously(failure_lesson):
    triple = any(
        joint["provenance"]["observed"] is True
        and joint["provenance"]["interpolated"] is True
        and joint["provenance"]["suppressed"] is not None
        for sample in failure_lesson["persons"][0]["samples"]
        for joint in sample["joints"]
    )
    assert triple, "fixture must contain at least one joint sample with all three provenance flags active at once"


def test_rejects_missing_schema_version(good_lesson):
    doc = copy.deepcopy(good_lesson)
    del doc["schema_version"]
    result = validate_motion_result(doc)
    assert result.valid is False


def test_rejects_non_monotonic_sample_times(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["sample_times_s"][5] = doc["sample_times_s"][4]
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("strictly increasing" in e for e in result.errors)


def test_rejects_samples_length_mismatch(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["persons"][0]["samples"].pop()
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("samples length" in e for e in result.errors)


def test_rejects_root_trajectory_length_mismatch(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["persons"][0]["root_trajectory"].pop()
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("root_trajectory length" in e for e in result.errors)


def test_rejects_joint_count_mismatch_within_a_sample(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["persons"][0]["samples"][0]["joints"].pop()
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("joints length" in e for e in result.errors)


def test_rejects_absent_joint_with_no_suppression_reason(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["persons"][0]["samples"][0]["joints"][0]["visibility"] = "absent"
    doc["persons"][0]["samples"][0]["joints"][0]["provenance"]["suppressed"] = None
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any('visibility "absent"' in e for e in result.errors)


def test_rejects_grounding_none_with_floor_plane(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["grounding"]["status"] = "none"
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any('grounding.status is "none"' in e for e in result.errors)


def test_rejects_grounding_grounded_with_null_floor_plane(failure_lesson):
    doc = copy.deepcopy(failure_lesson)
    doc["grounding"]["status"] = "grounded"
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("floor_plane is null" in e for e in result.errors)


def test_rejects_joint_index_mismatch(good_lesson):
    doc = copy.deepcopy(good_lesson)
    doc["joint_hierarchy"]["joints"][3]["index"] = 99
    result = validate_motion_result(doc)
    assert result.valid is False
    assert any("must equal 3" in e for e in result.errors)


def test_job_status_minimal_queued_job_is_valid():
    result = validate_job_status(
        {
            "schema_version": "1.0.0",
            "job_id": "job_abc",
            "state": "queued",
            "stage_message": "",
            "progress": None,
            "error": None,
            "retry_count": 0,
        }
    )
    assert result.errors == []
    assert result.valid is True


def test_job_status_rejects_unknown_state():
    result = validate_job_status(
        {
            "schema_version": "1.0.0",
            "job_id": "job_abc",
            "state": "bogus",
            "stage_message": "",
            "progress": None,
            "error": None,
            "retry_count": 0,
        }
    )
    assert result.valid is False
