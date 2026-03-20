"""Difficulty scoring from joint velocity.

Overall difficulty is derived from the sum of joint velocities across frames,
normalized to [0, 1]. Per-frame difficulty captures instantaneous movement
intensity.
"""

from __future__ import annotations

import math

from pipeline.models.schema import Difficulty, DifficultyFrame, FramePose

try:
    from pipeline.models.schema import BodyPartDifficulty, BodyPartDifficultyFrame, BodyPartScores
except ImportError:
    # Temporary: will be imported from schema.py after Task 1 completes
    from pydantic import BaseModel, Field

    class BodyPartScores(BaseModel):  # type: ignore[no-redef]
        arms: float = Field(ge=0, le=1)
        legs: float = Field(ge=0, le=1)
        core: float = Field(ge=0, le=1)

    class BodyPartDifficultyFrame(BaseModel):  # type: ignore[no-redef]
        frame: int = Field(ge=0)
        overall: float = Field(ge=0, le=1)
        body_parts: BodyPartScores

    class BodyPartDifficulty(BaseModel):  # type: ignore[no-redef]
        overall: float = Field(ge=0, le=1)
        per_frame: list[BodyPartDifficultyFrame]


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


# ---------------------------------------------------------------------------
# Per-body-part difficulty scoring
# ---------------------------------------------------------------------------

# Body part groupings for per-region difficulty scoring.
# All 24 SMPL joints: arms (10), legs (8), core (6).
BODY_PART_GROUPS: dict[str, set[str]] = {
    "arms": {
        "left_shoulder", "right_shoulder",
        "left_elbow", "right_elbow",
        "left_wrist", "right_wrist",
        "left_hand", "right_hand",
        "left_collar", "right_collar",
    },
    "legs": {
        "left_hip", "right_hip",
        "left_knee", "right_knee",
        "left_ankle", "right_ankle",
        "left_foot", "right_foot",
    },
    "core": {
        "pelvis", "spine1", "spine2", "spine3",
        "neck", "head",
    },
}


def _joint_velocities(
    pose_prev: FramePose,
    pose_curr: FramePose,
    dt: float,
) -> dict[str, float]:
    """Compute velocity magnitude for each named joint."""
    velocities: dict[str, float] = {}
    for j_prev, j_curr in zip(pose_prev.joints, pose_curr.joints):
        dx = (j_curr.x - j_prev.x) / dt
        dy = (j_curr.y - j_prev.y) / dt
        dz = (j_curr.z - j_prev.z) / dt
        velocities[j_curr.name] = math.sqrt(dx * dx + dy * dy + dz * dz)
    return velocities


def compute_body_part_difficulty(
    poses: list[FramePose],
    fps: float,
) -> BodyPartDifficulty:
    """Compute per-body-part difficulty scores.

    Groups joints into arms, legs, and core regions, computes the sum of
    joint velocities per region, then normalizes each region independently.
    """
    if len(poses) < 2:
        return BodyPartDifficulty(
            overall=0.0,
            per_frame=[
                BodyPartDifficultyFrame(
                    frame=p.frame, overall=0.0,
                    body_parts=BodyPartScores(arms=0.0, legs=0.0, core=0.0),
                ) for p in poses
            ],
        )

    dt = 1.0 / fps if fps > 0 else 1.0 / 30.0

    # Compute raw velocities per body part per frame
    raw_arms: list[float] = [0.0]
    raw_legs: list[float] = [0.0]
    raw_core: list[float] = [0.0]

    for i in range(1, len(poses)):
        velocities = _joint_velocities(poses[i - 1], poses[i], dt)
        raw_arms.append(sum(v for name, v in velocities.items() if name in BODY_PART_GROUPS["arms"]))
        raw_legs.append(sum(v for name, v in velocities.items() if name in BODY_PART_GROUPS["legs"]))
        raw_core.append(sum(v for name, v in velocities.items() if name in BODY_PART_GROUPS["core"]))

    # Normalize each region independently to [0, 1]
    def _normalize(raw: list[float]) -> list[float]:
        max_val = max(raw) if raw else 1.0
        if max_val <= 0:
            return [0.0] * len(raw)
        return [min(1.0, v / max_val) for v in raw]

    norm_arms = _normalize(raw_arms)
    norm_legs = _normalize(raw_legs)
    norm_core = _normalize(raw_core)

    per_frame: list[BodyPartDifficultyFrame] = []
    for i, pose in enumerate(poses):
        overall = (norm_arms[i] + norm_legs[i] + norm_core[i]) / 3.0
        per_frame.append(BodyPartDifficultyFrame(
            frame=pose.frame,
            overall=round(overall, 4),
            body_parts=BodyPartScores(
                arms=round(norm_arms[i], 4),
                legs=round(norm_legs[i], 4),
                core=round(norm_core[i], 4),
            ),
        ))

    total_overall = sum(df.overall for df in per_frame) / len(per_frame)

    return BodyPartDifficulty(
        overall=round(total_overall, 4),
        per_frame=per_frame,
    )
