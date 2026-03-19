"""Difficulty scoring from joint velocity.

Overall difficulty is derived from the sum of joint velocities across frames,
normalized to [0, 1]. Per-frame difficulty captures instantaneous movement
intensity.
"""

from __future__ import annotations

import math

from pipeline.models.schema import Difficulty, DifficultyFrame, FramePose


def _joint_velocity_magnitude(
    pose_prev: FramePose,
    pose_curr: FramePose,
    dt: float,
) -> float:
    """Sum of all joint velocity magnitudes between two frames."""
    total = 0.0
    for j_prev, j_curr in zip(pose_prev.joints, pose_curr.joints):
        dx = (j_curr.x - j_prev.x) / dt
        dy = (j_curr.y - j_prev.y) / dt
        dz = (j_curr.z - j_prev.z) / dt
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def compute_difficulty(
    poses: list[FramePose],
    fps: float,
) -> Difficulty:
    """Compute difficulty scores from joint velocities.

    Per-frame score is the sum of all joint velocity magnitudes, normalized
    to [0, 1] by dividing by the maximum observed value. Overall difficulty
    is the mean of per-frame scores.

    Args:
        poses: Per-frame body poses.
        fps: Frames per second.

    Returns:
        Difficulty with overall and per-frame scores.
    """
    if len(poses) < 2:
        return Difficulty(
            overall=0.0,
            per_frame=[DifficultyFrame(frame=p.frame, score=0.0) for p in poses],
        )

    dt = 1.0 / fps if fps > 0 else 1.0 / 30.0

    # Compute raw velocity sums
    raw_scores: list[float] = [0.0]  # First frame has no velocity
    for i in range(1, len(poses)):
        raw_scores.append(_joint_velocity_magnitude(poses[i - 1], poses[i], dt))

    # Normalize to [0, 1]
    max_score = max(raw_scores) if raw_scores else 1.0
    if max_score <= 0:
        max_score = 1.0

    per_frame: list[DifficultyFrame] = []
    for i, pose in enumerate(poses):
        normalized = min(1.0, raw_scores[i] / max_score)
        per_frame.append(DifficultyFrame(
            frame=pose.frame,
            score=round(normalized, 4),
        ))

    overall = sum(df.score for df in per_frame) / len(per_frame)

    return Difficulty(
        overall=round(overall, 4),
        per_frame=per_frame,
    )
