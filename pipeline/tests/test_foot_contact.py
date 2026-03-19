"""Tests for foot contact heuristics."""

from __future__ import annotations

import pytest

from pipeline.models.schema import ContactType, FramePose, Joint3D
from pipeline.services.foot_contact import (
    AIRBORNE_Y_THRESHOLD,
    FLOOR_Y_THRESHOLD,
    compute_foot_contacts,
)
from pipeline.services.pose_extractor import SMPL_JOINT_NAMES, _BASE_POSITIONS


def _make_pose(
    frame: int,
    fps: float = 30.0,
    left_ankle_y: float = 0.08,
    right_ankle_y: float = 0.08,
    left_foot_y: float = 0.02,
    right_foot_y: float = 0.02,
    left_ankle_x: float = 0.09,
    right_ankle_x: float = -0.09,
) -> FramePose:
    """Create a pose with configurable ankle/foot positions."""
    joints = []
    for name in SMPL_JOINT_NAMES:
        bx, by, bz = _BASE_POSITIONS[name]
        if name == "left_ankle":
            joints.append(Joint3D(name=name, x=left_ankle_x, y=left_ankle_y, z=0.0))
        elif name == "right_ankle":
            joints.append(Joint3D(name=name, x=right_ankle_x, y=right_ankle_y, z=0.0))
        elif name == "left_foot":
            joints.append(Joint3D(name=name, x=0.09, y=left_foot_y, z=0.05))
        elif name == "right_foot":
            joints.append(Joint3D(name=name, x=-0.09, y=right_foot_y, z=0.05))
        else:
            joints.append(Joint3D(name=name, x=bx, y=by, z=bz))
    return FramePose(frame=frame, timestamp=frame / fps, joints=joints)


class TestFootContactClassification:
    def test_standing_flat(self):
        """Both feet on the ground, no movement -> flat."""
        poses = [
            _make_pose(0, left_ankle_y=0.08, right_ankle_y=0.08, left_foot_y=0.07, right_foot_y=0.07),
            _make_pose(1, left_ankle_y=0.08, right_ankle_y=0.08, left_foot_y=0.07, right_foot_y=0.07),
        ]
        contacts = compute_foot_contacts(poses, fps=30.0)
        assert contacts[0].left.contact == ContactType.FLAT
        assert contacts[0].right.contact == ContactType.FLAT
        assert contacts[1].left.contact == ContactType.FLAT
        assert contacts[1].right.contact == ContactType.FLAT

    def test_airborne(self):
        """Ankles well above floor -> airborne."""
        poses = [
            _make_pose(0, left_ankle_y=0.08, right_ankle_y=0.08),
            _make_pose(1, left_ankle_y=0.50, right_ankle_y=0.50),
        ]
        contacts = compute_foot_contacts(poses, fps=30.0)
        assert contacts[1].left.contact == ContactType.AIRBORNE
        assert contacts[1].right.contact == ContactType.AIRBORNE

    def test_slide(self):
        """Ankle near floor with large horizontal velocity -> slide."""
        poses = [
            _make_pose(0, left_ankle_x=0.0),
            _make_pose(1, left_ankle_x=0.05),  # 0.05m in 1/30s = 1.5 m/s
        ]
        contacts = compute_foot_contacts(poses, fps=30.0)
        assert contacts[1].left.contact == ContactType.SLIDE

    def test_heel_contact(self):
        """Ankle on floor but foot (toe) elevated -> heel."""
        poses = [
            _make_pose(0, left_ankle_y=0.06, left_foot_y=0.10),
            _make_pose(1, left_ankle_y=0.06, left_foot_y=0.10),
        ]
        contacts = compute_foot_contacts(poses, fps=30.0)
        assert contacts[1].left.contact == ContactType.HEEL

    def test_toe_contact(self):
        """Ankle between thresholds, moderate vertical speed."""
        poses = [
            _make_pose(0, left_ankle_y=0.15),
            _make_pose(1, left_ankle_y=0.15),
        ]
        contacts = compute_foot_contacts(poses, fps=30.0)
        # Between FLOOR and AIRBORNE thresholds, low vert speed -> toe
        assert contacts[1].left.contact == ContactType.TOE

    def test_frame_count_matches(self):
        """Output should have same number of entries as input poses."""
        poses = [_make_pose(i) for i in range(10)]
        contacts = compute_foot_contacts(poses, fps=30.0)
        assert len(contacts) == 10


class TestFromMockPoses:
    def test_mock_poses_produce_valid_contacts(self):
        """Foot contacts from the mock pose generator should all be valid."""
        from pipeline.services.pose_extractor import _generate_mock_movement

        poses = _generate_mock_movement(30, 30.0)
        contacts = compute_foot_contacts(poses, 30.0)
        assert len(contacts) == 30
        valid_types = set(ContactType)
        for c in contacts:
            assert c.left.contact in valid_types
            assert c.right.contact in valid_types
