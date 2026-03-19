"""Tests for difficulty computation."""

from __future__ import annotations

import pytest

from pipeline.models.schema import FramePose, Joint3D
from pipeline.services.difficulty import compute_difficulty
from pipeline.services.pose_extractor import SMPL_JOINT_NAMES, _BASE_POSITIONS


def _make_static_pose(frame: int, fps: float = 30.0) -> FramePose:
    """Create a pose at the T-pose (no movement)."""
    joints = [
        Joint3D(name=name, x=pos[0], y=pos[1], z=pos[2])
        for name, pos in _BASE_POSITIONS.items()
    ]
    return FramePose(frame=frame, timestamp=frame / fps, joints=joints)


def _make_shifted_pose(
    frame: int, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, fps: float = 30.0
) -> FramePose:
    """Create a pose with all joints shifted by (dx, dy, dz)."""
    joints = [
        Joint3D(name=name, x=pos[0] + dx, y=pos[1] + dy, z=pos[2] + dz)
        for name, pos in _BASE_POSITIONS.items()
    ]
    return FramePose(frame=frame, timestamp=frame / fps, joints=joints)


class TestDifficultyComputation:
    def test_single_frame_zero_difficulty(self):
        """A single frame has no velocity, so difficulty should be 0."""
        poses = [_make_static_pose(0)]
        diff = compute_difficulty(poses, fps=30.0)
        assert diff.overall == 0.0
        assert len(diff.per_frame) == 1
        assert diff.per_frame[0].score == 0.0

    def test_static_sequence_zero_difficulty(self):
        """No movement across frames -> all zeros."""
        poses = [_make_static_pose(i) for i in range(10)]
        diff = compute_difficulty(poses, fps=30.0)
        assert diff.overall == 0.0
        for df in diff.per_frame:
            assert df.score == 0.0

    def test_moving_sequence_nonzero_difficulty(self):
        """Movement between frames should produce nonzero difficulty."""
        poses = [
            _make_static_pose(0),
            _make_shifted_pose(1, dx=0.1),
            _make_shifted_pose(2, dx=0.2),
        ]
        diff = compute_difficulty(poses, fps=30.0)
        assert diff.overall > 0.0
        # First frame should be 0 (no previous frame)
        assert diff.per_frame[0].score == 0.0
        # Subsequent frames should be nonzero
        assert diff.per_frame[1].score > 0.0
        assert diff.per_frame[2].score > 0.0

    def test_scores_bounded_0_to_1(self):
        """All scores should be in [0, 1]."""
        poses = [_make_static_pose(0)]
        for i in range(1, 20):
            poses.append(_make_shifted_pose(i, dx=i * 0.05, dy=i * 0.02))
        diff = compute_difficulty(poses, fps=30.0)
        assert 0.0 <= diff.overall <= 1.0
        for df in diff.per_frame:
            assert 0.0 <= df.score <= 1.0

    def test_max_frame_has_score_1(self):
        """The frame with maximum velocity should have score = 1.0."""
        poses = [
            _make_static_pose(0),
            _make_shifted_pose(1, dx=0.01),  # small movement
            _make_shifted_pose(2, dx=0.5),   # big jump
            _make_shifted_pose(3, dx=0.51),  # tiny movement
        ]
        diff = compute_difficulty(poses, fps=30.0)
        scores = [df.score for df in diff.per_frame]
        assert max(scores) == 1.0

    def test_frame_indices_match(self):
        """Per-frame entries should have correct frame indices."""
        poses = [_make_static_pose(i) for i in range(5)]
        diff = compute_difficulty(poses, fps=30.0)
        for i, df in enumerate(diff.per_frame):
            assert df.frame == i


class TestDifficultyFromMockPoses:
    def test_mock_poses_produce_valid_difficulty(self):
        """Difficulty from mock pose generator should be valid."""
        from pipeline.services.pose_extractor import _generate_mock_movement

        poses = _generate_mock_movement(60, 30.0)
        diff = compute_difficulty(poses, 30.0)
        assert 0.0 < diff.overall < 1.0  # Should have some movement
        assert len(diff.per_frame) == 60
