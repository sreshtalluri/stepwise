"""Tests for Pydantic model validation against the JSON schema."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.models.schema import (
    Beat,
    BodyPartDifficulty,
    BodyPartDifficultyFrame,
    BodyPartScores,
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
    PersonPose,
    SmplxParams,
    StepwiseResult,
    StepwiseResultV2,
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


class TestSmplxParams:
    def test_valid_smplx_params(self):
        """SMPL-X format: 63-value body_pose with hand poses."""
        params = SmplxParams(
            betas=[0.0] * 10,
            body_pose=[0.0] * 63,
            left_hand_pose=[0.0] * 45,
            right_hand_pose=[0.0] * 45,
            global_orient=[0.0, 0.0, 0.0],
            transl=[0.0, 0.95, 0.0],
        )
        assert len(params.betas) == 10
        assert len(params.body_pose) == 63

    def test_valid_smpl_params(self):
        """SMPL format: 69-value body_pose, no hand poses."""
        params = SmplxParams(
            betas=[0.0] * 10,
            body_pose=[0.0] * 69,
            global_orient=[0.0, 0.0, 0.0],
            transl=[0.0, 0.95, 0.0],
        )
        assert len(params.body_pose) == 69
        assert params.left_hand_pose == []
        assert params.right_hand_pose == []

    def test_rejects_wrong_body_pose_length(self):
        with pytest.raises(Exception):
            SmplxParams(
                betas=[0.0] * 10,
                body_pose=[0.0] * 50,  # wrong: need 63-69
                global_orient=[0.0, 0.0, 0.0],
                transl=[0.0, 0.0, 0.0],
            )

    def test_rejects_wrong_betas_length(self):
        with pytest.raises(Exception):
            SmplxParams(
                betas=[0.0] * 5,  # wrong: need 10
                body_pose=[0.0] * 63,
                global_orient=[0.0, 0.0, 0.0],
                transl=[0.0, 0.0, 0.0],
            )


class TestPersonPose:
    def test_valid_person_pose(self):
        params = SmplxParams(
            betas=[0.0] * 10,
            body_pose=[0.0] * 63,
            left_hand_pose=[0.0] * 45,
            right_hand_pose=[0.0] * 45,
            global_orient=[0.0, 0.0, 0.0],
            transl=[0.0, 0.0, 0.0],
        )
        person = PersonPose(
            person_id=0,
            frame=0,
            timestamp=0.0,
            smplx_params=params,
        )
        assert person.person_id == 0


class TestBodyPartDifficulty:
    def test_valid_body_part_difficulty_frame(self):
        scores = BodyPartScores(arms=0.3, legs=0.8, core=0.5)
        df = BodyPartDifficultyFrame(frame=0, overall=0.5, body_parts=scores)
        assert df.body_parts.arms == 0.3
        assert df.body_parts.legs == 0.8

    def test_scores_bounded(self):
        with pytest.raises(Exception):
            BodyPartScores(arms=1.5, legs=0.0, core=0.0)


class TestStepwiseResultV2:
    def _minimal_v2_result(self) -> dict:
        return {
            "version": "2.0",
            "video_id": "test123",
            "url_hash": "abc" * 20 + "ab",
            "source_url": "https://youtube.com/watch?v=test123",
            "duration_seconds": 10.0,
            "fps": 30.0,
            "total_frames": 1,
            "body_poses": [{
                "frame": 0, "timestamp": 0.0,
                "joints": [{"name": f"joint_{i}", "x": 0.0, "y": 0.0, "z": 0.0} for i in range(24)],
            }],
            "hand_states": [{
                "frame": 0, "timestamp": 0.0,
                "left": {"detected": False, "gesture": "none", "confidence": 0.0},
                "right": {"detected": False, "gesture": "none", "confidence": 0.0},
            }],
            "foot_contacts": [{
                "frame": 0, "timestamp": 0.0,
                "left": {"contact": "flat"}, "right": {"contact": "flat"},
            }],
            "beats": [],
            "difficulty": {"overall": 0.0, "per_frame": [{"frame": 0, "score": 0.0}]},
            "processed_at": "2026-01-15T12:00:00Z",
            "person_count": 1,
            "person_poses": [{
                "person_id": 0, "frame": 0, "timestamp": 0.0,
                "smplx_params": {
                    "betas": [0.0] * 10, "body_pose": [0.0] * 63,
                    "left_hand_pose": [0.0] * 45, "right_hand_pose": [0.0] * 45,
                    "global_orient": [0.0, 0.0, 0.0], "transl": [0.0, 0.0, 0.0],
                },
            }],
            "body_part_difficulty": {
                "overall": 0.0,
                "per_frame": [{"frame": 0, "overall": 0.0, "body_parts": {"arms": 0.0, "legs": 0.0, "core": 0.0}}],
            },
        }

    def test_valid_v2_result(self):
        data = self._minimal_v2_result()
        result = StepwiseResultV2.model_validate(data)
        assert result.version == "2.0"
        assert result.person_count == 1

    def test_v2_backward_compatible_with_v1_fields(self):
        """V2 must still contain all v1 fields (body_poses, hand_states, etc.)."""
        data = self._minimal_v2_result()
        result = StepwiseResultV2.model_validate(data)
        assert len(result.body_poses) == 1
        assert len(result.hand_states) == 1
