"""Tests for Pydantic model validation against the JSON schema."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.models.schema import (
    Beat,
    ContactType,
    Difficulty,
    DifficultyFrame,
    FootContact,
    FootContactType,
    FramePose,
    GestureType,
    HandGesture,
    HandState,
    Joint3D,
    StepwiseResult,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestGoldenFixture:
    """Validate the golden fixture against the Pydantic model."""

    def test_golden_fixture_loads(self):
        with open(FIXTURES_DIR / "golden_result.json") as f:
            data = json.load(f)
        result = StepwiseResult.model_validate(data)
        assert result.version == "1.0"

    def test_golden_fixture_has_correct_frame_count(self):
        with open(FIXTURES_DIR / "golden_result.json") as f:
            data = json.load(f)
        result = StepwiseResult.model_validate(data)
        assert result.total_frames == 30
        assert len(result.body_poses) == 30
        assert len(result.hand_states) == 30
        assert len(result.foot_contacts) == 30

    def test_golden_fixture_joint_count(self):
        with open(FIXTURES_DIR / "golden_result.json") as f:
            data = json.load(f)
        result = StepwiseResult.model_validate(data)
        for pose in result.body_poses:
            assert len(pose.joints) == 24

    def test_golden_fixture_roundtrip(self):
        with open(FIXTURES_DIR / "golden_result.json") as f:
            data = json.load(f)
        result = StepwiseResult.model_validate(data)
        roundtripped = json.loads(result.model_dump_json())
        result2 = StepwiseResult.model_validate(roundtripped)
        assert result2.video_id == result.video_id
        assert len(result2.body_poses) == len(result.body_poses)


class TestStepwiseResultValidation:
    """Test validation constraints on the Pydantic model."""

    def _minimal_result(self, **overrides) -> dict:
        base = {
            "version": "1.0",
            "video_id": "test123",
            "url_hash": "abc" * 20 + "ab",
            "source_url": "https://youtube.com/watch?v=test123",
            "duration_seconds": 10.0,
            "fps": 30.0,
            "total_frames": 1,
            "body_poses": [
                {
                    "frame": 0,
                    "timestamp": 0.0,
                    "joints": [
                        {"name": f"joint_{i}", "x": 0.0, "y": 0.0, "z": 0.0}
                        for i in range(24)
                    ],
                }
            ],
            "hand_states": [
                {
                    "frame": 0,
                    "timestamp": 0.0,
                    "left": {"detected": False, "gesture": "none", "confidence": 0.0},
                    "right": {"detected": False, "gesture": "none", "confidence": 0.0},
                }
            ],
            "foot_contacts": [
                {
                    "frame": 0,
                    "timestamp": 0.0,
                    "left": {"contact": "flat"},
                    "right": {"contact": "flat"},
                }
            ],
            "beats": [],
            "difficulty": {"overall": 0.0, "per_frame": [{"frame": 0, "score": 0.0}]},
            "processed_at": "2026-01-15T12:00:00Z",
        }
        base.update(overrides)
        return base

    def test_valid_minimal_result(self):
        data = self._minimal_result()
        result = StepwiseResult.model_validate(data)
        assert result.version == "1.0"

    def test_rejects_wrong_version(self):
        data = self._minimal_result(version="2.0")
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_rejects_duration_over_120(self):
        data = self._minimal_result(duration_seconds=121.0)
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_rejects_negative_fps(self):
        data = self._minimal_result(fps=-1)
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_rejects_wrong_joint_count(self):
        data = self._minimal_result()
        data["body_poses"][0]["joints"] = [
            {"name": f"j{i}", "x": 0, "y": 0, "z": 0} for i in range(10)
        ]
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_rejects_invalid_gesture(self):
        data = self._minimal_result()
        data["hand_states"][0]["left"]["gesture"] = "dab"
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_rejects_invalid_contact_type(self):
        data = self._minimal_result()
        data["foot_contacts"][0]["left"]["contact"] = "moonwalk"
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)

    def test_difficulty_score_bounds(self):
        data = self._minimal_result()
        data["difficulty"]["overall"] = 1.5
        with pytest.raises(Exception):
            StepwiseResult.model_validate(data)
