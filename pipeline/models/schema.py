"""Pydantic models matching schema/stepwise-result.json."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Joint3D(BaseModel):
    name: str
    x: float
    y: float
    z: float


class FramePose(BaseModel):
    frame: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    joints: list[Joint3D] = Field(min_length=24, max_length=24)
    joints_3d: list[Joint3D] | None = Field(default=None, min_length=24, max_length=24)


class GestureType(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    POINTING = "pointing"
    PEACE = "peace"
    UNKNOWN = "unknown"
    NONE = "none"


class HandGesture(BaseModel):
    detected: bool
    gesture: GestureType
    confidence: float = Field(default=0.0, ge=0, le=1)


class HandState(BaseModel):
    frame: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    left: HandGesture
    right: HandGesture


class ContactType(str, Enum):
    FLAT = "flat"
    TOE = "toe"
    HEEL = "heel"
    AIRBORNE = "airborne"
    SLIDE = "slide"


class FootContactType(BaseModel):
    contact: ContactType


class FootContact(BaseModel):
    frame: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    left: FootContactType
    right: FootContactType


class Beat(BaseModel):
    timestamp: float = Field(ge=0)
    strength: float = Field(ge=0, le=1)


class DifficultyFrame(BaseModel):
    frame: int = Field(ge=0)
    score: float = Field(ge=0, le=1)


class Difficulty(BaseModel):
    overall: float = Field(ge=0, le=1)
    per_frame: list[DifficultyFrame]


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


class StepwiseResult(BaseModel):
    version: Literal["1.0"] = "1.0"
    video_id: str
    url_hash: str
    source_url: str
    duration_seconds: float = Field(ge=0, le=120)
    fps: float = Field(gt=0)
    total_frames: int = Field(ge=1)
    body_poses: list[FramePose]
    hand_states: list[HandState]
    foot_contacts: list[FootContact]
    beats: list[Beat]
    difficulty: Difficulty
    processed_at: datetime


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
