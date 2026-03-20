"""SMPL-X body model extraction with mock fallback.

Set USE_REAL_SMPLX=true to use 4D Humans (requires model weights).
Otherwise, generates plausible mock SMPL-X parameters.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from pipeline.models.schema import PersonPose, SmplxParams
except ImportError:
    # Temporary: these will be in schema.py after Task 1 completes
    from pydantic import BaseModel, Field

    class SmplxParams(BaseModel):  # type: ignore[no-redef]
        """SMPL-X body model parameters for one person in one frame."""
        betas: list[float] = Field(min_length=10, max_length=10)
        body_pose: list[float] = Field(min_length=63, max_length=63)
        left_hand_pose: list[float] = Field(min_length=45, max_length=45)
        right_hand_pose: list[float] = Field(min_length=45, max_length=45)
        global_orient: list[float] = Field(min_length=3, max_length=3)
        transl: list[float] = Field(min_length=3, max_length=3)

    class PersonPose(BaseModel):  # type: ignore[no-redef]
        """SMPL-X params for one person in one frame."""
        person_id: int = Field(ge=0)
        frame: int = Field(ge=0)
        timestamp: float = Field(ge=0)
        smplx_params: SmplxParams


@dataclass
class SmplxExtractionResult:
    """Result of SMPL-X extraction for all persons across all frames."""
    person_count: int
    person_poses: list[PersonPose] = field(default_factory=list)


def _generate_mock_smplx(
    total_frames: int,
    fps: float,
    num_people: int = 1,
) -> SmplxExtractionResult:
    """Generate plausible mock SMPL-X parameters.

    Creates smooth motion by varying body_pose and transl sinusoidally.
    Each person gets a fixed body shape (betas) and varying poses.
    """
    person_poses: list[PersonPose] = []
    cycle_frames = int(fps * 2)  # 2-second movement cycle

    for person_id in range(num_people):
        # Fixed body shape per person (slight variation)
        betas = [0.0] * 10
        betas[0] = (person_id - num_people / 2) * 0.5  # height variation

        # Lateral offset so people don't overlap
        base_x = (person_id - (num_people - 1) / 2) * 0.8

        for frame_idx in range(total_frames):
            t = frame_idx / fps
            phase = (frame_idx % cycle_frames) / cycle_frames
            angle = math.sin(phase * 2 * math.pi)

            # Body pose: 21 joints x 3 axis-angle = 63 values
            # Animate shoulders (joints 16,17 in SMPL ordering -> indices 48-53)
            body_pose = [0.0] * 63
            body_pose[48] = angle * 0.5   # left shoulder Z rotation
            body_pose[51] = -angle * 0.5  # right shoulder Z rotation
            # Slight hip sway
            body_pose[0] = math.sin(phase * 4 * math.pi) * 0.1

            # Hands: relaxed open pose with slight variation
            left_hand = [0.0] * 45
            right_hand = [0.0] * 45
            for i in range(0, 45, 3):
                left_hand[i] = math.sin(phase * 2 * math.pi + i * 0.1) * 0.1
                right_hand[i] = math.sin(phase * 2 * math.pi + i * 0.1 + 0.5) * 0.1

            # Global orientation: facing forward with slight rotation
            global_orient = [0.0, math.sin(phase * 2 * math.pi) * 0.1, 0.0]

            # Translation: slight lateral sway
            transl = [
                base_x + math.sin(phase * 4 * math.pi) * 0.05,
                0.95,
                0.0,
            ]

            params = SmplxParams(
                betas=betas,
                body_pose=[round(v, 4) for v in body_pose],
                left_hand_pose=[round(v, 4) for v in left_hand],
                right_hand_pose=[round(v, 4) for v in right_hand],
                global_orient=[round(v, 4) for v in global_orient],
                transl=[round(v, 4) for v in transl],
            )

            person_poses.append(PersonPose(
                person_id=person_id,
                frame=frame_idx,
                timestamp=round(t, 4),
                smplx_params=params,
            ))

    return SmplxExtractionResult(
        person_count=num_people,
        person_poses=person_poses,
    )


async def extract_smplx(
    video_path: str | Path,
    total_frames: int,
    fps: float,
    num_people: int = 1,
) -> SmplxExtractionResult:
    """Extract SMPL-X body params from video.

    Uses 4D Humans when USE_REAL_SMPLX=true, otherwise returns mock data.
    """
    use_real = os.environ.get("USE_REAL_SMPLX", "false").lower() in ("true", "1", "yes")

    if use_real:
        raise NotImplementedError(
            "Real SMPL-X extraction requires 4D Humans model weights. "
            "Set USE_REAL_SMPLX=false or omit to use mock data."
        )

    return _generate_mock_smplx(total_frames, fps, num_people)
