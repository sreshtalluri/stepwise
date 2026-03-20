"""Tests for per-body-part difficulty scoring."""

from __future__ import annotations

import pytest

from pipeline.models.schema import FramePose, Joint3D
from pipeline.services.difficulty import compute_body_part_difficulty, BODY_PART_GROUPS
from pipeline.services.pose_extractor import SMPL_JOINT_NAMES, _BASE_POSITIONS


def _make_static_pose(frame: int, fps: float = 30.0) -> FramePose:
    joints = [
        Joint3D(name=name, x=pos[0], y=pos[1], z=pos[2])
        for name, pos in _BASE_POSITIONS.items()
    ]
    return FramePose(frame=frame, timestamp=frame / fps, joints=joints)


def _make_arms_moving_pose(frame: int, dx: float, fps: float = 30.0) -> FramePose:
    """Only arm joints move, legs and core stay static."""
    arm_joints = BODY_PART_GROUPS["arms"]
    joints = []
    for name in SMPL_JOINT_NAMES:
        pos = _BASE_POSITIONS[name]
        if name in arm_joints:
            joints.append(Joint3D(name=name, x=pos[0] + dx, y=pos[1], z=pos[2]))
        else:
            joints.append(Joint3D(name=name, x=pos[0], y=pos[1], z=pos[2]))
    return FramePose(frame=frame, timestamp=frame / fps, joints=joints)


class TestBodyPartGroups:
    def test_all_joints_assigned(self):
        """Every SMPL joint must belong to exactly one body part group."""
        all_grouped = set()
        for joints in BODY_PART_GROUPS.values():
            all_grouped.update(joints)
        assert all_grouped == set(SMPL_JOINT_NAMES)

    def test_no_overlapping_groups(self):
        """No joint should appear in more than one group."""
        seen = set()
        for joints in BODY_PART_GROUPS.values():
            overlap = seen & set(joints)
            assert overlap == set(), f"Overlapping joints: {overlap}"
            seen.update(joints)


class TestBodyPartDifficulty:
    def test_static_sequence_all_zero(self):
        poses = [_make_static_pose(i) for i in range(5)]
        diff = compute_body_part_difficulty(poses, fps=30.0)
        assert diff.overall == 0.0
        for df in diff.per_frame:
            assert df.body_parts.arms == 0.0
            assert df.body_parts.legs == 0.0
            assert df.body_parts.core == 0.0

    def test_arms_only_movement(self):
        """When only arms move, arms difficulty should be high, legs/core near zero."""
        poses = [_make_static_pose(0)]
        for i in range(1, 5):
            poses.append(_make_arms_moving_pose(i, dx=i * 0.1))
        diff = compute_body_part_difficulty(poses, fps=30.0)
        # Check a frame with movement
        frame_with_movement = diff.per_frame[2]
        assert frame_with_movement.body_parts.arms > 0.0
        assert frame_with_movement.body_parts.legs == 0.0
        assert frame_with_movement.body_parts.core == 0.0

    def test_scores_bounded(self):
        poses = [_make_static_pose(0)]
        for i in range(1, 10):
            poses.append(_make_arms_moving_pose(i, dx=i * 0.2))
        diff = compute_body_part_difficulty(poses, fps=30.0)
        for df in diff.per_frame:
            assert 0.0 <= df.body_parts.arms <= 1.0
            assert 0.0 <= df.body_parts.legs <= 1.0
            assert 0.0 <= df.body_parts.core <= 1.0
            assert 0.0 <= df.overall <= 1.0

    def test_frame_count_matches(self):
        poses = [_make_static_pose(i) for i in range(8)]
        diff = compute_body_part_difficulty(poses, fps=30.0)
        assert len(diff.per_frame) == 8
