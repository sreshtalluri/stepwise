"""MotionBERT wrapper — mock implementation returning realistic fake pose data.

When the real MotionBERT model is available, replace the mock with actual
inference. The interface stays the same: video path in, list of FramePose out.
"""

from __future__ import annotations

import math
from pathlib import Path

from pipeline.models.schema import FramePose, Joint3D


# 24 SMPL joint names in standard order
SMPL_JOINT_NAMES = [
    "pelvis", "left_hip", "right_hip", "spine1",
    "left_knee", "right_knee", "spine2",
    "left_ankle", "right_ankle", "spine3",
    "left_foot", "right_foot", "neck",
    "left_collar", "right_collar", "head",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hand", "right_hand",
]

# Base T-pose positions for SMPL skeleton (approximate, in meters)
_BASE_POSITIONS: dict[str, tuple[float, float, float]] = {
    "pelvis":          (0.0,   0.95, 0.0),
    "left_hip":        (0.09,  0.90, 0.0),
    "right_hip":       (-0.09, 0.90, 0.0),
    "spine1":          (0.0,   1.05, 0.0),
    "left_knee":       (0.09,  0.50, 0.0),
    "right_knee":      (-0.09, 0.50, 0.0),
    "spine2":          (0.0,   1.15, 0.0),
    "left_ankle":      (0.09,  0.08, 0.0),
    "right_ankle":     (-0.09, 0.08, 0.0),
    "spine3":          (0.0,   1.25, 0.0),
    "left_foot":       (0.09,  0.02, 0.05),
    "right_foot":      (-0.09, 0.02, 0.05),
    "neck":            (0.0,   1.45, 0.0),
    "left_collar":     (0.05,  1.40, 0.0),
    "right_collar":    (-0.05, 1.40, 0.0),
    "head":            (0.0,   1.60, 0.0),
    "left_shoulder":   (0.18,  1.40, 0.0),
    "right_shoulder":  (-0.18, 1.40, 0.0),
    "left_elbow":      (0.40,  1.40, 0.0),
    "right_elbow":     (-0.40, 1.40, 0.0),
    "left_wrist":      (0.60,  1.40, 0.0),
    "right_wrist":     (-0.60, 1.40, 0.0),
    "left_hand":       (0.65,  1.40, 0.0),
    "right_hand":      (-0.65, 1.40, 0.0),
}


def _generate_mock_movement(
    total_frames: int,
    fps: float,
) -> list[FramePose]:
    """Generate a realistic mock movement: arms raising/lowering with body sway.

    The animation cycles through:
    - Arms raise from sides to overhead and back (2-second cycle)
    - Slight body sway side-to-side
    - Knees bend slightly on the beat
    """
    frames: list[FramePose] = []
    cycle_frames = int(fps * 2)  # 2-second cycle

    for i in range(total_frames):
        t = i / fps  # time in seconds
        phase = (i % cycle_frames) / cycle_frames  # 0..1 over cycle
        arm_angle = math.sin(phase * 2 * math.pi) * 0.5 + 0.5  # 0..1
        sway = math.sin(phase * 4 * math.pi) * 0.03  # lateral sway
        knee_bend = max(0, math.sin(phase * 4 * math.pi)) * 0.05

        joints: list[Joint3D] = []
        for name in SMPL_JOINT_NAMES:
            bx, by, bz = _BASE_POSITIONS[name]
            x, y, z = bx, by, bz

            # Apply lateral sway to upper body
            if "spine" in name or "neck" in name or "head" in name or "shoulder" in name or "collar" in name:
                x += sway

            # Animate arms: raise from sides to overhead
            if name in ("left_shoulder", "left_elbow", "left_wrist", "left_hand"):
                angle = arm_angle * math.pi  # 0 to pi
                dist_from_shoulder = abs(bx - 0.18) + abs(by - 1.40)
                if dist_from_shoulder < 0.01:
                    pass  # shoulder stays
                else:
                    # Rotate arm upward
                    rel_x = bx - 0.18
                    rel_y = by - 1.40
                    length = math.sqrt(rel_x**2 + rel_y**2)
                    base_angle = math.atan2(rel_y, rel_x)
                    new_angle = base_angle + angle
                    x = 0.18 + length * math.cos(new_angle) + sway
                    y = 1.40 + length * math.sin(new_angle)

            if name in ("right_shoulder", "right_elbow", "right_wrist", "right_hand"):
                angle = arm_angle * math.pi
                dist_from_shoulder = abs(bx - (-0.18)) + abs(by - 1.40)
                if dist_from_shoulder < 0.01:
                    pass
                else:
                    rel_x = bx - (-0.18)
                    rel_y = by - 1.40
                    length = math.sqrt(rel_x**2 + rel_y**2)
                    base_angle = math.atan2(rel_y, rel_x)
                    new_angle = base_angle + (math.pi - angle)
                    x = -0.18 + length * math.cos(new_angle) + sway
                    y = 1.40 + length * math.sin(new_angle)

            # Knee bend
            if "knee" in name:
                y -= knee_bend
                z += knee_bend * 0.5
            if "ankle" in name or "foot" in name:
                y -= knee_bend * 0.3

            joints.append(Joint3D(name=name, x=round(x, 4), y=round(y, 4), z=round(z, 4)))

        frames.append(FramePose(
            frame=i,
            timestamp=round(t, 4),
            joints=joints,
        ))

    return frames


async def extract_poses(
    video_path: Path,
    total_frames: int,
    fps: float,
) -> list[FramePose]:
    """Extract 3D body poses from video.

    Currently uses mock data. Replace with MotionBERT inference when available.

    Args:
        video_path: Path to the video file.
        total_frames: Number of frames to generate poses for.
        fps: Frames per second of the video.

    Returns:
        List of FramePose, one per frame, each with 24 SMPL joints.
    """
    # TODO: Replace with actual MotionBERT inference
    return _generate_mock_movement(total_frames, fps)
