# SMPL-X Phase 1: Pipeline + Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the processing pipeline to support SMPL-X body model params alongside existing skeleton data, with progressive enhancement (skeleton first, mannequin later) and per-body-part difficulty scoring.

**Architecture:** The pipeline gains a two-pass strategy: MediaPipe runs first (~10s) to produce v1 skeleton data, then a SMPL-X extractor (mock for now) runs second (~90s) to produce v2 params. The job status endpoint gains a state machine (processing → skeleton_ready → upgrading → mannequin_ready). Schema v2 adds per-person SMPL params while staying backward-compatible with v1.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest. Worktree at `/Users/sreshtalluri/Documents/Github/stepwise-smplx`, branch `feat/smplx-mannequin`. Use pyenv virtualenv `stepwise`.

---

## File Structure

```
pipeline/
├── models/
│   └── schema.py              # MODIFY — add v2 models (SmplxParams, PersonPose, BodyPartDifficulty, StepwiseResultV2)
├── services/
│   ├── smplx_extractor.py     # CREATE — SMPL-X extraction with mock fallback
│   └── difficulty.py          # MODIFY — add per-body-part scoring
├── app.py                     # MODIFY — state machine, progressive enhancement pipeline
├── tests/
│   ├── test_schema.py         # MODIFY — add v2 schema tests
│   ├── test_smplx_extractor.py # CREATE — tests for SMPL-X extractor
│   ├── test_difficulty_v2.py  # CREATE — tests for per-body-part difficulty
│   └── test_pipeline_state.py # CREATE — tests for job state machine
frontend/
└── lib/
    └── types.ts               # MODIFY — add SMPL-X TypeScript types, v2 status response
```

---

### Task 1: Schema V2 — SMPL-X Pydantic Models

**Files:**
- Modify: `pipeline/models/schema.py`
- Modify: `pipeline/tests/test_schema.py`

The schema gains new models for SMPL params per person per frame, and a v2 result type that includes both the v1 skeleton data and v2 SMPL data. The v1 `StepwiseResult` stays untouched for backward compatibility.

- [ ] **Step 1: Write failing tests for v2 schema models**

Add to `pipeline/tests/test_schema.py`:

```python
import pytest

from pipeline.models.schema import (
    SmplxParams,
    PersonPose,
    BodyPartScores,
    BodyPartDifficultyFrame,
    BodyPartDifficulty,
    StepwiseResultV2,
)


class TestSmplxParams:
    def test_valid_smplx_params(self):
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

    def test_rejects_wrong_betas_length(self):
        with pytest.raises(Exception):
            SmplxParams(
                betas=[0.0] * 5,  # wrong: need 10
                body_pose=[0.0] * 63,
                left_hand_pose=[0.0] * 45,
                right_hand_pose=[0.0] * 45,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && pyenv activate stepwise && python -m pytest pipeline/tests/test_schema.py -v -k "Smplx or PersonPose or BodyPart or V2" 2>&1 | head -30`

Expected: ImportError — classes don't exist yet.

- [ ] **Step 3: Implement v2 schema models in schema.py**

Add the following models to `pipeline/models/schema.py` (after the existing `Difficulty` class, before `StepwiseResult`):

```python
class SmplxParams(BaseModel):
    """SMPL-X body model parameters for one person in one frame."""
    betas: list[float] = Field(min_length=10, max_length=10)
    body_pose: list[float] = Field(min_length=63, max_length=63)
    left_hand_pose: list[float] = Field(min_length=45, max_length=45)
    right_hand_pose: list[float] = Field(min_length=45, max_length=45)
    global_orient: list[float] = Field(min_length=3, max_length=3)
    transl: list[float] = Field(min_length=3, max_length=3)


class PersonPose(BaseModel):
    """SMPL-X params for one person in one frame."""
    person_id: int = Field(ge=0)
    frame: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    smplx_params: SmplxParams


class BodyPartScores(BaseModel):
    """Per-body-part difficulty scores for one frame."""
    arms: float = Field(ge=0, le=1)
    legs: float = Field(ge=0, le=1)
    core: float = Field(ge=0, le=1)


class BodyPartDifficultyFrame(BaseModel):
    """Per-frame difficulty with body-part breakdown."""
    frame: int = Field(ge=0)
    overall: float = Field(ge=0, le=1)
    body_parts: BodyPartScores


class BodyPartDifficulty(BaseModel):
    """Difficulty with per-body-part breakdown."""
    overall: float = Field(ge=0, le=1)
    per_frame: list[BodyPartDifficultyFrame]


class StepwiseResultV2(BaseModel):
    """V2 result with SMPL-X params and per-body-part difficulty.

    Extends v1 fields (body_poses, hand_states, etc.) for backward compatibility.
    The v1 body_poses field contains skeleton data from the MediaPipe fast pass.
    """
    version: Literal["2.0"] = "2.0"
    video_id: str
    url_hash: str
    source_url: str
    duration_seconds: float = Field(ge=0, le=120)
    fps: float = Field(gt=0)
    total_frames: int = Field(ge=1)
    # V1 fields (from MediaPipe fast pass)
    body_poses: list[FramePose]
    hand_states: list[HandState]
    foot_contacts: list[FootContact]
    beats: list[Beat]
    difficulty: Difficulty
    # V2 additions
    person_count: int = Field(ge=1)
    person_poses: list[PersonPose]
    body_part_difficulty: BodyPartDifficulty
    processed_at: datetime
```

Also update the `Literal` import at the top to include `"2.0"`:
Change `from typing import Literal` — no change needed, the Literal is used per-class.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_schema.py -v 2>&1 | tail -20`

Expected: All tests PASS, including existing v1 tests (backward compatible).

- [ ] **Step 5: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add pipeline/models/schema.py pipeline/tests/test_schema.py
git commit -m "feat: add schema v2 models for SMPL-X params and body-part difficulty"
```

---

### Task 2: Per-Body-Part Difficulty Scoring

**Files:**
- Modify: `pipeline/services/difficulty.py`
- Create: `pipeline/tests/test_difficulty_v2.py`

Extend the existing difficulty service to group joints by body region (arms, legs, core) and compute separate scores per region. The existing `compute_difficulty()` function stays unchanged — we add a new `compute_body_part_difficulty()` alongside it.

- [ ] **Step 1: Write failing tests for body-part difficulty**

Create `pipeline/tests/test_difficulty_v2.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_difficulty_v2.py -v 2>&1 | head -20`

Expected: ImportError — `BODY_PART_GROUPS` and `compute_body_part_difficulty` don't exist.

- [ ] **Step 3: Implement body-part difficulty in difficulty.py**

Add to `pipeline/services/difficulty.py`:

```python
from pipeline.models.schema import (
    BodyPartDifficulty,
    BodyPartDifficultyFrame,
    BodyPartScores,
    Difficulty,
    DifficultyFrame,
    FramePose,
)

# Body part groupings for per-region difficulty scoring
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
    """Compute velocity magnitude for each named joint.

    Also used by _joint_velocity_magnitude (refactored to share this).
    """
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
```

- [ ] **Step 4: Run all difficulty tests**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_difficulty.py pipeline/tests/test_difficulty_v2.py -v`

Expected: All tests PASS (both old and new).

- [ ] **Step 5: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add pipeline/services/difficulty.py pipeline/tests/test_difficulty_v2.py
git commit -m "feat: add per-body-part difficulty scoring (arms, legs, core)"
```

---

### Task 3: SMPL-X Extractor with Mock Fallback

**Files:**
- Create: `pipeline/services/smplx_extractor.py`
- Create: `pipeline/tests/test_smplx_extractor.py`

New module following the same pattern as `pose_extractor.py` — mock by default, real model when `USE_REAL_SMPLX=true`. The mock generates plausible SMPL-X params for 1-3 people with smooth motion.

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/test_smplx_extractor.py`:

```python
"""Tests for SMPL-X extraction (mock mode)."""

from __future__ import annotations

import pytest

from pipeline.services.smplx_extractor import extract_smplx, SmplxExtractionResult


class TestSmplxExtractionResult:
    def test_result_has_person_count(self):
        result = SmplxExtractionResult(person_count=2, person_poses=[])
        assert result.person_count == 2


class TestMockSmplxExtraction:
    @pytest.mark.asyncio
    async def test_returns_result(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        assert result.person_count >= 1

    @pytest.mark.asyncio
    async def test_frame_count_matches(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=60,
            fps=30.0,
        )
        # Each person should have total_frames entries
        person_0_frames = [p for p in result.person_poses if p.person_id == 0]
        assert len(person_0_frames) == 60

    @pytest.mark.asyncio
    async def test_params_have_correct_dimensions(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=10,
            fps=30.0,
        )
        for person_pose in result.person_poses:
            p = person_pose.smplx_params
            assert len(p.betas) == 10
            assert len(p.body_pose) == 63
            assert len(p.left_hand_pose) == 45
            assert len(p.right_hand_pose) == 45
            assert len(p.global_orient) == 3
            assert len(p.transl) == 3

    @pytest.mark.asyncio
    async def test_person_ids_are_stable(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        person_ids = {p.person_id for p in result.person_poses}
        # Mock generates 1-3 people; IDs should be sequential from 0
        assert 0 in person_ids

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        person_0 = [p for p in result.person_poses if p.person_id == 0]
        timestamps = [p.timestamp for p in person_0]
        assert timestamps == sorted(timestamps)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_smplx_extractor.py -v 2>&1 | head -15`

Expected: ImportError — module doesn't exist.

- [ ] **Step 3: Implement SMPL-X extractor**

Create `pipeline/services/smplx_extractor.py`:

```python
"""SMPL-X body model extraction with mock fallback.

Set USE_REAL_SMPLX=true to use 4D Humans (requires model weights).
Otherwise, generates plausible mock SMPL-X parameters.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.models.schema import PersonPose, SmplxParams


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

            # Body pose: 21 joints × 3 axis-angle = 63 values
            # Animate shoulders (joints 16,17 in SMPL ordering → indices 48-53)
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
```

- [ ] **Step 4: Install pytest-asyncio if needed and run tests**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && pip install pytest-asyncio 2>/dev/null; python -m pytest pipeline/tests/test_smplx_extractor.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add pipeline/services/smplx_extractor.py pipeline/tests/test_smplx_extractor.py
git commit -m "feat: add SMPL-X extractor service with mock fallback"
```

---

### Task 4: Pipeline State Machine

**Files:**
- Modify: `pipeline/app.py`
- Create: `pipeline/tests/test_pipeline_state.py`

Update the job status model from simple `"processing" | "complete" | "error"` to a state machine: `processing → skeleton_ready → upgrading → mannequin_ready`. The `/status` endpoint gains new fields for the progressive enhancement flow.

- [ ] **Step 1: Write failing tests for state machine**

Create `pipeline/tests/test_pipeline_state.py`:

```python
"""Tests for pipeline job state machine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.app import app, _jobs, JobStatusResponse


client = TestClient(app)


class TestJobStatusResponse:
    def test_status_includes_skeleton_url(self):
        """When skeleton is ready, response should include skeleton_result_url."""
        _jobs["test-1"] = {
            "status": "skeleton_ready",
            "step": "Enhancing with SMPL-X...",
            "result_url": None,
            "skeleton_result_url": "https://r2.example.com/skeleton.json",
            "mannequin_result_url": None,
            "error": None,
        }
        response = client.get("/status/test-1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skeleton_ready"
        assert data["skeleton_result_url"] == "https://r2.example.com/skeleton.json"

    def test_mannequin_ready_includes_both_urls(self):
        """When mannequin is ready, both skeleton and mannequin URLs should be present."""
        _jobs["test-2"] = {
            "status": "mannequin_ready",
            "step": None,
            "result_url": "https://r2.example.com/skeleton.json",
            "skeleton_result_url": "https://r2.example.com/skeleton.json",
            "mannequin_result_url": "https://r2.example.com/mannequin.json",
            "error": None,
        }
        response = client.get("/status/test-2")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "mannequin_ready"
        assert data["mannequin_result_url"] is not None

    def test_backward_compatible_complete_status(self):
        """Old 'complete' status should still work for v1 results."""
        _jobs["test-3"] = {
            "status": "complete",
            "step": None,
            "result_url": "https://r2.example.com/result.json",
            "skeleton_result_url": None,
            "mannequin_result_url": None,
            "error": None,
        }
        response = client.get("/status/test-3")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"

    def test_not_found(self):
        response = client.get("/status/nonexistent")
        assert response.status_code == 404


class TestHealthEndpoint:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_pipeline_state.py -v 2>&1 | head -20`

Expected: Failures because `JobStatusResponse` doesn't have the new fields.

- [ ] **Step 3: Update JobStatusResponse and job store in app.py**

In `pipeline/app.py`, update `JobStatusResponse`:

```python
class JobStatusResponse(BaseModel):
    status: str  # "processing" | "skeleton_ready" | "upgrading" | "mannequin_ready" | "complete" | "error"
    step: str | None = None
    result_url: str | None = None
    skeleton_result_url: str | None = None
    mannequin_result_url: str | None = None
    error: str | None = None
```

Update the `get_job_status` endpoint to include the new fields:

```python
@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    return JobStatusResponse(
        status=job["status"],
        step=job.get("step"),
        result_url=job.get("result_url"),
        skeleton_result_url=job.get("skeleton_result_url"),
        mannequin_result_url=job.get("mannequin_result_url"),
        error=job.get("error"),
    )
```

Update the job initialization in `process_video` to include new fields:

```python
_jobs[job_id] = {
    "status": "processing",
    "step": "Downloading video...",
    "result_url": None,
    "skeleton_result_url": None,
    "mannequin_result_url": None,
    "error": None,
}
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_pipeline_state.py -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add pipeline/app.py pipeline/tests/test_pipeline_state.py
git commit -m "feat: add progressive enhancement state machine to job status"
```

---

### Task 5: Progressive Enhancement Pipeline

**Files:**
- Modify: `pipeline/app.py`

Wire the two-pass pipeline: MediaPipe first → upload v1 → set `skeleton_ready` → SMPL-X second → upload v2 → set `mannequin_ready`. Note: `process_video_sync` is intentionally left as-is (v1 only) — it's the backward-compatible sync endpoint. Progressive enhancement only applies to the async pipeline.

- [ ] **Step 1: Refactor _run_pipeline to use progressive enhancement**

Replace the existing `_run_pipeline` function in `pipeline/app.py` with:

```python
from pipeline.services.smplx_extractor import extract_smplx
from pipeline.models.schema import StepwiseResult, StepwiseResultV2

async def _run_pipeline(job_id: str, url: str) -> None:
    """Run the progressive enhancement pipeline.

    Pass 1 (fast): MediaPipe → skeleton data → upload v1 → status: skeleton_ready
    Pass 2 (slow): SMPL-X → mannequin data → upload v2 → status: mannequin_ready
    """
    job = _jobs[job_id]

    try:
        # 0. Resolve short links
        if is_tiktok_shortlink(url):
            try:
                url = await resolve_shortlink(url)
            except InvalidURLError as e:
                job["status"] = "error"
                job["error"] = str(e)
                return

        # 1. Validate URL
        job["step"] = "Downloading video..."
        try:
            platform, video_id = extract_video_id(url)
            computed_hash = url_hash(url)
        except (InvalidURLError, UnsupportedPlatformError) as e:
            job["status"] = "error"
            job["error"] = str(e)
            return

        # 2. Check cache (v2 first, fall back to v1)
        try:
            cached = await check_cache(computed_hash)
            if cached is not None:
                signed_url = await get_signed_url(computed_hash)
                job["status"] = "complete"
                job["result_url"] = signed_url
                job["skeleton_result_url"] = signed_url
                return
        except Exception:
            pass

        # 3. Download video
        try:
            video_info = await download_video(url)
        except VideoTooLongError as e:
            job["status"] = "error"
            job["error"] = str(e)
            return
        except DownloadError as e:
            job["status"] = "error"
            job["error"] = str(e)
            return

        # =====================================================================
        # PASS 1: MediaPipe fast pass → skeleton (v1)
        # =====================================================================
        job["step"] = "Extracting poses..."

        poses_task = extract_poses(
            video_info.video_path, video_info.total_frames, video_info.fps
        )
        hands_task = detect_hands(
            video_info.video_path, video_info.total_frames, video_info.fps
        )
        beats_task = detect_beats(
            video_info.audio_path, video_info.duration_seconds
        )

        poses, hand_states, beats = await asyncio.gather(
            poses_task, hands_task, beats_task
        )

        foot_contacts = compute_foot_contacts(poses, video_info.fps)
        difficulty = compute_difficulty(poses, video_info.fps)

        result_v1 = StepwiseResult(
            version="1.0",
            video_id=video_info.video_id,
            url_hash=computed_hash,
            source_url=url,
            duration_seconds=video_info.duration_seconds,
            fps=video_info.fps,
            total_frames=video_info.total_frames,
            body_poses=poses,
            hand_states=hand_states,
            foot_contacts=foot_contacts,
            beats=beats,
            difficulty=difficulty,
            processed_at=datetime.now(timezone.utc),
        )

        # Upload v1 skeleton result
        try:
            await upload_result(computed_hash, result_v1)
            skeleton_url = await get_signed_url(computed_hash)
            job["skeleton_result_url"] = skeleton_url
            job["result_url"] = skeleton_url
        except Exception:
            job["status"] = "error"
            job["error"] = "Failed to upload skeleton result"
            return

        # Upload video to R2
        try:
            await upload_video(computed_hash, str(video_info.video_path))
        except Exception:
            pass  # Video upload failure shouldn't block

        job["status"] = "skeleton_ready"
        job["step"] = "Enhancing with SMPL-X..."

        # =====================================================================
        # PASS 2: SMPL-X full pass → mannequin (v2)
        # =====================================================================
        try:
            smplx_result = await extract_smplx(
                video_info.video_path,
                video_info.total_frames,
                video_info.fps,
            )

            job["status"] = "upgrading"
            job["step"] = "Analyzing movement detail..."

            body_part_diff = compute_body_part_difficulty(poses, video_info.fps)

            result_v2 = StepwiseResultV2(
                version="2.0",
                video_id=video_info.video_id,
                url_hash=computed_hash,
                source_url=url,
                duration_seconds=video_info.duration_seconds,
                fps=video_info.fps,
                total_frames=video_info.total_frames,
                body_poses=poses,
                hand_states=hand_states,
                foot_contacts=foot_contacts,
                beats=beats,
                difficulty=difficulty,
                person_count=smplx_result.person_count,
                person_poses=smplx_result.person_poses,
                body_part_difficulty=body_part_diff,
                processed_at=datetime.now(timezone.utc),
            )

            # Upload v2 with a different R2 key so v1 is preserved
            from pipeline.services.storage import _get_r2_client, BUCKET_NAME
            v2_key = f"{computed_hash}/v2.0.json"
            client = _get_r2_client()
            client.put_object(
                Bucket=BUCKET_NAME,
                Key=v2_key,
                Body=result_v2.model_dump_json(indent=2),
                ContentType="application/json",
            )
            mannequin_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": v2_key},
                ExpiresIn=3600,
            )
            job["mannequin_result_url"] = mannequin_url
            job["result_url"] = mannequin_url
            job["status"] = "mannequin_ready"

        except NotImplementedError:
            # Real SMPL-X not available yet — stay on skeleton
            job["status"] = "skeleton_ready"
        except Exception:
            # SMPL-X failed — stay on skeleton, which is already available
            job["status"] = "skeleton_ready"

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
```

Also add the new imports at the top of `app.py`:

```python
from pipeline.services.smplx_extractor import extract_smplx
from pipeline.services.difficulty import compute_body_part_difficulty
from pipeline.models.schema import StepwiseResult, StepwiseResultV2
```

- [ ] **Step 2: Run all tests to verify nothing broke**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/ -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add pipeline/app.py
git commit -m "feat: wire progressive enhancement pipeline (skeleton → mannequin)"
```

---

### Task 6: Frontend TypeScript Types

**Files:**
- Modify: `frontend/lib/types.ts`

Add SMPL-X param types and update `StatusResponse` to include the progressive enhancement fields. No rendering changes — just type definitions for Phase 2.

- [ ] **Step 1: Add SMPL-X types to types.ts**

Add the following types to `frontend/lib/types.ts`:

```typescript
// SMPL-X body model parameters (v2)
export interface SmplxParams {
  betas: number[];        // body shape (10 values)
  body_pose: number[];    // joint rotations (63 values = 21 joints × 3)
  left_hand_pose: number[];  // left hand joints (45 values = 15 joints × 3)
  right_hand_pose: number[]; // right hand joints (45 values = 15 joints × 3)
  global_orient: number[];   // root orientation (3 values)
  transl: number[];          // root translation (3 values)
}

export interface PersonPose {
  person_id: number;
  frame: number;
  timestamp: number;
  smplx_params: SmplxParams;
}

export interface BodyPartScores {
  arms: number;  // 0-1
  legs: number;  // 0-1
  core: number;  // 0-1
}

export interface BodyPartDifficultyFrame {
  frame: number;
  overall: number;  // 0-1
  body_parts: BodyPartScores;
}

export interface BodyPartDifficulty {
  overall: number;
  per_frame: BodyPartDifficultyFrame[];
}

export interface StepwiseResultV2 extends Omit<StepwiseResult, "version"> {
  version: "2.0";
  person_count: number;
  person_poses: PersonPose[];
  body_part_difficulty: BodyPartDifficulty;
}
```

Update `StatusResponse` to include progressive enhancement fields:

```typescript
export interface StatusResponse {
  status: "processing" | "skeleton_ready" | "upgrading" | "mannequin_ready" | "complete" | "error";
  step?: string;
  result_url?: string;
  skeleton_result_url?: string;
  mannequin_result_url?: string;
  error_message?: string;
  error?: string;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx/frontend && npx tsc --noEmit lib/types.ts 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/sreshtalluri/Documents/Github/stepwise-smplx
git add frontend/lib/types.ts
git commit -m "feat: add SMPL-X TypeScript types for Phase 2 mannequin renderer"
```

---

### Task 7: Final Integration Test

**Files:**
- All pipeline tests

Run the full test suite to confirm everything works together and nothing is broken.

- [ ] **Step 1: Run all pipeline tests**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/ -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /Users/sreshtalluri/Documents/Github/stepwise-smplx && python -m pytest pipeline/tests/test_schema.py pipeline/tests/test_difficulty.py -v`

Expected: All existing v1 tests still PASS (backward compatibility).

- [ ] **Step 3: Commit any final fixes if needed**

Only if tests revealed issues. Otherwise, Phase 1 is complete.
