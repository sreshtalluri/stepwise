"""Heuristic foot contact classification from 3D pose data.

Uses ankle position and velocity to determine contact type:
- flat: ankle near floor, low velocity
- toe: ankle slightly elevated, foot angled
- heel: ankle near floor, foot tilted back
- airborne: ankle well above floor
- slide: ankle near floor, significant horizontal velocity
"""

from __future__ import annotations

import math

from pipeline.models.schema import (
    FootContact,
    FootContactType,
    ContactType,
    FramePose,
)


# Thresholds (in meters, approximate)
FLOOR_Y_THRESHOLD = 0.12       # Below this = near floor
AIRBORNE_Y_THRESHOLD = 0.20    # Above this = airborne
VELOCITY_SLIDE_THRESHOLD = 0.8  # Horizontal velocity for slide (m/s)
VELOCITY_STILL_THRESHOLD = 0.2  # Below this = stationary


def _joint_position(pose: FramePose, joint_name: str) -> tuple[float, float, float]:
    """Get (x, y, z) position of a named joint."""
    for joint in pose.joints:
        if joint.name == joint_name:
            return (joint.x, joint.y, joint.z)
    raise ValueError(f"Joint {joint_name} not found in pose")


def _velocity(
    pos_prev: tuple[float, float, float],
    pos_curr: tuple[float, float, float],
    dt: float,
) -> tuple[float, float, float]:
    """Compute velocity vector between two positions."""
    if dt <= 0:
        return (0.0, 0.0, 0.0)
    return (
        (pos_curr[0] - pos_prev[0]) / dt,
        (pos_curr[1] - pos_prev[1]) / dt,
        (pos_curr[2] - pos_prev[2]) / dt,
    )


def _horizontal_speed(vel: tuple[float, float, float]) -> float:
    """Compute horizontal speed (xz plane)."""
    return math.sqrt(vel[0] ** 2 + vel[2] ** 2)


def _classify_foot(
    y: float,
    vel: tuple[float, float, float],
    foot_y: float,
) -> ContactType:
    """Classify foot contact based on ankle position and velocity.

    Args:
        y: Ankle y position.
        vel: Ankle velocity (x, y, z).
        foot_y: Foot (toe) y position.
    """
    h_speed = _horizontal_speed(vel)
    vert_speed = abs(vel[1])

    # High off the ground -> airborne
    if y > AIRBORNE_Y_THRESHOLD:
        return ContactType.AIRBORNE

    # Near floor
    if y <= FLOOR_Y_THRESHOLD:
        # Fast horizontal movement -> slide
        if h_speed > VELOCITY_SLIDE_THRESHOLD:
            return ContactType.SLIDE

        # Check if foot is tilted (toe vs heel)
        if foot_y > y + 0.03:
            return ContactType.HEEL
        elif foot_y < y - 0.02:
            return ContactType.TOE

        return ContactType.FLAT

    # Between floor and airborne thresholds
    if vert_speed > 0.5:
        return ContactType.AIRBORNE

    return ContactType.TOE


def compute_foot_contacts(
    poses: list[FramePose],
    fps: float,
) -> list[FootContact]:
    """Compute foot contact type for each frame.

    Args:
        poses: Per-frame body poses with 24 SMPL joints.
        fps: Frames per second (for velocity computation).

    Returns:
        List of FootContact, one per frame.
    """
    dt = 1.0 / fps if fps > 0 else 1.0 / 30.0
    contacts: list[FootContact] = []

    for i, pose in enumerate(poses):
        left_ankle = _joint_position(pose, "left_ankle")
        right_ankle = _joint_position(pose, "right_ankle")
        left_foot = _joint_position(pose, "left_foot")
        right_foot = _joint_position(pose, "right_foot")

        if i > 0:
            prev_left_ankle = _joint_position(poses[i - 1], "left_ankle")
            prev_right_ankle = _joint_position(poses[i - 1], "right_ankle")
            left_vel = _velocity(prev_left_ankle, left_ankle, dt)
            right_vel = _velocity(prev_right_ankle, right_ankle, dt)
        else:
            left_vel = (0.0, 0.0, 0.0)
            right_vel = (0.0, 0.0, 0.0)

        left_contact = _classify_foot(left_ankle[1], left_vel, left_foot[1])
        right_contact = _classify_foot(right_ankle[1], right_vel, right_foot[1])

        contacts.append(FootContact(
            frame=pose.frame,
            timestamp=pose.timestamp,
            left=FootContactType(contact=left_contact),
            right=FootContactType(contact=right_contact),
        ))

    return contacts
