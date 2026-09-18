# GENERATED FILE — do not edit by hand.
# Source of truth: packages/motion-contract/schema/*.schema.json
# Regenerate with: bash scripts/generate-python.sh

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    RootModel,
    confloat,
    conint,
    constr,
)


class Vec3(RootModel[list[float]]):
    """
    [x, y, z], meters, world space unless stated otherwise by the containing field.
    """

    root: list[float] = Field(
        ...,
        description='[x, y, z], meters, world space unless stated otherwise by the containing field.',
        max_length=3,
        min_length=3,
    )


class Quaternion(RootModel[list[float]]):
    """
    [x, y, z, w] rotation quaternion, glTF/three.js component order (NOT [w,x,y,z]). Never filter or interpolate these components as independent scalars — PRD §4 requires filtering on unwrapped scalar joint angles upstream and re-deriving the quaternion, precisely because naive quaternion-component filtering produces invalid rotations.
    """

    root: list[float] = Field(
        ...,
        description='[x, y, z, w] rotation quaternion, glTF/three.js component order (NOT [w,x,y,z]). Never filter or interpolate these components as independent scalars — PRD §4 requires filtering on unwrapped scalar joint angles upstream and re-deriving the quaternion, precisely because naive quaternion-component filtering produces invalid rotations.',
        max_length=4,
        min_length=4,
    )


class Mat4(RootModel[list[float]]):
    """
    4x4 transform, 16 numbers, COLUMN-MAJOR (glTF convention: elements 0-3 are column 0, i.e. index = col*4 + row).
    """

    root: list[float] = Field(
        ...,
        description='4x4 transform, 16 numbers, COLUMN-MAJOR (glTF convention: elements 0-3 are column 0, i.e. index = col*4 + row).',
        max_length=16,
        min_length=16,
    )


class RotationDeg(Enum):
    """
    Clockwise rotation already baked into width_px/height_px and every crop rectangle during ingest normalization (e.g. phone EXIF orientation). width_px/height_px describe the frame AFTER this rotation is applied — consumers never re-apply it.
    """

    int_0 = 0
    int_90 = 90
    int_180 = 180
    int_270 = 270


class SourceVideo(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    asset_id: constr(min_length=1) = Field(
        ...,
        description='Immutable id of the normalized source video asset. Never a signed/expiring URL — resolve the id to a fetchable URL via a separate, short-lived lookup at render time.',
    )
    width_px: PositiveInt = Field(
        ..., description='Normalized (post-rotation) frame width in pixels.'
    )
    height_px: PositiveInt = Field(
        ..., description='Normalized (post-rotation) frame height in pixels.'
    )
    rotation_deg: RotationDeg = Field(
        ...,
        description='Clockwise rotation already baked into width_px/height_px and every crop rectangle during ingest normalization (e.g. phone EXIF orientation). width_px/height_px describe the frame AFTER this rotation is applied — consumers never re-apply it.',
    )
    duration_s: PositiveFloat = Field(
        ...,
        description='Normalized clip duration in seconds. May be less than sample_times_s[-1] + one frame period only by rounding; treat sample_times_s as authoritative.',
    )
    fps_nominal: PositiveFloat = Field(
        ...,
        description="The nominal ingest sampling rate (PRD §3: 15 fps). INFORMATIONAL ONLY — display/debug use. Never use this to derive a sample's timestamp; use sample_times_s.",
    )
    audio_offset_s: float = Field(
        ...,
        description='Seconds to add to a video timeline time to get the corresponding audio-track time. Positive means the audio track starts later than the video track. Needed because ingest normalization (§3) can shift audio/video sync.',
    )


class Intrinsics(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    fx: float = Field(
        ...,
        description='Focal length, x, in pixels, at reference_width_px/reference_height_px resolution.',
    )
    fy: float = Field(..., description='Focal length, y, in pixels.')
    cx: float = Field(..., description='Principal point x, in pixels.')
    cy: float = Field(..., description='Principal point y, in pixels.')
    reference_width_px: PositiveInt = Field(
        ...,
        description='Pixel width these intrinsics were computed at. Scale fx/fy/cx/cy proportionally if rendering at a different resolution than source_video.width_px.',
    )
    reference_height_px: PositiveInt


class Camera(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    model: Literal['pinhole'] = Field(
        ...,
        description='v1 supports a single static pinhole camera per clip (PRD §5: moving cameras are explicitly out of v1 scope). One camera for the whole clip, not one per sample.',
    )
    intrinsics: Intrinsics
    camera_to_world: Mat4 = Field(
        ...,
        description='Static camera-to-world transform for the whole clip (see `model`). 4x4, column-major, meters. World space is the same space root_trajectory and floor_plane are expressed in.',
    )


class Status(Enum):
    """
    "none" when feet were cropped/occluded for enough of the clip that a floor fit is not trustworthy (PRD §4). When "none", the renderer must show the figure floating with no floor plane at all — DESIGN.md §10 explicitly forbids faking a plane.
    """

    grounded = 'grounded'
    none = 'none'


class FloorPlane(BaseModel):
    """
    Required to be null when status is "none"; required to be a plane when status is "grounded".
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    normal: Vec3 = Field(
        ...,
        description='Unit normal of the floor plane, world space, pointing up (+Y-ish).',
    )
    point: Vec3 = Field(..., description='A point on the floor plane, world space.')


class Grounding(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    status: Status = Field(
        ...,
        description='"none" when feet were cropped/occluded for enough of the clip that a floor fit is not trustworthy (PRD §4). When "none", the renderer must show the figure floating with no floor plane at all — DESIGN.md §10 explicitly forbids faking a plane.',
    )
    floor_plane: FloorPlane | None = Field(
        ...,
        description='Required to be null when status is "none"; required to be a plane when status is "grounded".',
    )


class Source(Enum):
    """
    "sampled": median hue of the middle third of frames, clamped to the DESIGN.md §3 S/L bounds. "fallback": one of the fixed --dancer-N swatches, used when sampling fails or there is more than one person (OPEN-DECISIONS.md E4 — sampling quality is still unproven).
    """

    sampled = 'sampled'
    fallback = 'fallback'


class AccentColor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    hex: constr(pattern=r'^#[0-9A-Fa-f]{6}$') = Field(
        ...,
        description='sRGB hex, e.g. "#E8952F". Persisted here so the viewer and the auto-generated share clip (DESIGN.md §7g) always agree, per DESIGN.md §3.',
    )
    source: Source = Field(
        ...,
        description='"sampled": median hue of the middle third of frames, clamped to the DESIGN.md §3 S/L bounds. "fallback": one of the fixed --dancer-N swatches, used when sampling fails or there is more than one person (OPEN-DECISIONS.md E4 — sampling quality is still unproven).',
    )


class SuppressionReason(Enum):
    """
    null when not suppressed. "out_of_frame": the joint's region left the camera frame (case 3, DESIGN.md §7h — never render as recovered). "low_confidence": occluded or the estimator's confidence fell below threshold (case 2, DESIGN.md §7h — a person/object blocked the view, or, per the honesty-boundary nuance, a back-facing frame where depth is ambiguous).
    """

    NoneType_None = None
    out_of_frame = 'out_of_frame'
    low_confidence = 'low_confidence'


class Provenance(BaseModel):
    """
    The raw pipeline provenance for one joint on one sample. Deliberately kept separate from `visibility` (see JointSample) — provenance is what the pipeline did; visibility is what the renderer should show. They are not always the same shape of information and this contract never derives one from the other implicitly.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    observed: bool = Field(
        ...,
        description='True if the per-frame estimator directly produced a value for this joint on this sample (case 1 or a fully-visible case-2/3 region).',
    )
    interpolated: bool = Field(
        ...,
        description="True if this value was filled in by the Kalman/interpolation chain across a gap rather than taken directly from a single frame's estimate. Independent of `observed` and `suppressed` — PRD §4: a sample can be model-estimated AND interpolated AND suppressed at once (e.g. a smoothed value across a still-suppressed span).",
    )
    suppressed: SuppressionReason


class Visibility(Enum):
    """
    The DESIGN.md §4 three-state render taxonomy, stored explicitly rather than left for the viewer to derive from `provenance`. "observed": solid fill, casts shadow. "uncertain": desaturated, sketchy outline, stays attached to the body (case 1 back-facing ambiguity or case 2 occlusion). "absent": not drawn, stub + dotted continuation (case 3, out of frame). Honesty rule (DESIGN.md §7h): a joint whose provenance.suppressed is "low_confidence" while the person is simply turned away (case 1) should generally be "uncertain", never "absent" — case 1 is the product's best claim and must not be under-rendered as if nothing were tracked.
    """

    observed = 'observed'
    uncertain = 'uncertain'
    absent = 'absent'


class JointDef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    name: str = Field(
        ...,
        description='Canonical joint name, e.g. "left_shoulder". Stable across schema versions.',
    )
    index: conint(ge=0) = Field(
        ...,
        description='Position of this joint in every per-sample `joints` array in this document. `joint_hierarchy.joints[i].index === i` always.',
    )
    parent_index: conint(ge=-1) = Field(
        ...,
        description='Index (into joint_hierarchy.joints) of the parent joint, or -1 for the root.',
    )
    glb_node_name: str = Field(
        ...,
        description='The node name inside the GLB referenced by `animation.glb_asset_id` that this joint drives. Look up by name, not by scene-graph position — exporters are not guaranteed to preserve node order.',
    )
    rest_rotation: Quaternion = Field(
        ...,
        description="This joint's local-to-parent rotation in the MHR rest (A-pose) skeleton — the pose every per-sample rotation is relative to.",
    )
    rest_translation: Vec3 = Field(
        ...,
        description="This joint's local-to-parent translation (bone offset) in the rest pose, meters.",
    )


class JointHierarchy(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    rotation_convention: Literal[
        'local-to-parent quaternion, relative to MHR rest (A-pose), glTF component order [x,y,z,w]'
    ] = Field(
        ...,
        description='Every per-sample joint rotation in this document (persons[i].samples[j].joints[k].rotation) is a LOCAL rotation relative to its parent joint, expressed relative to this joint\'s rest_rotation — i.e. the identity quaternion means "exactly the rest pose," not "exactly aligned with the parent\'s axes." Root orientation in world space is `persons[i].root_trajectory[j].rotation`, not this.',
    )
    root_joint_index: conint(ge=0) = Field(
        ..., description='Index into `joints` of the pelvis/root joint.'
    )
    joints: list[JointDef] = Field(
        ...,
        description='Fixed for the life of schema v1.0.0 (MHR skeleton). Ordered by `index` ascending; every per-sample `joints` array elsewhere in this document has exactly this length, in this order.',
        min_length=1,
    )


class AnimationRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    clip_id: constr(min_length=1) = Field(
        ...,
        description='Name of the AnimationClip inside the referenced GLB (the name passed to `AnimationMixer.clipAction`).',
    )
    glb_asset_id: constr(min_length=1) = Field(
        ...,
        description='Immutable id of the exported GLB asset. Never a signed/expiring URL — resolve separately at render time, same as source_video.asset_id.',
    )


class CropRect1(BaseModel):
    """
    Normalized [0,1] rectangle, origin top-left, relative to source_video width_px/height_px AFTER rotation_deg is applied. x+width and y+height need not be <= 1 clamped by consumers, but SHOULD be within frame.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    x: confloat(ge=0.0, le=1.0)
    y: confloat(ge=0.0, le=1.0)
    width: confloat(le=1.0, gt=0.0)
    height: confloat(le=1.0, gt=0.0)


class RootTrajectorySample(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    position: Vec3 = Field(
        ...,
        description='World-space position of the root/pelvis joint, meters, in the same space as camera.camera_to_world and grounding.floor_plane.',
    )
    rotation: Quaternion = Field(
        ..., description='World-space orientation of the root/pelvis joint.'
    )
    provenance: Provenance


class JointSample(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    rotation: Quaternion = Field(
        ...,
        description='See joint_hierarchy.rotation_convention. Meaningless/should not be rendered when visibility is "absent" — a value is always present here (parametric body models always output something, PRD §4) but it is not a claim about ground truth.',
    )
    provenance: Provenance
    visibility: Visibility


class Sample(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    joints: list[JointSample] = Field(
        ...,
        description='Parallel to joint_hierarchy.joints — same length, same order, indexed the same way.',
        min_length=1,
    )


class Source1(Enum):
    """
    "default_assumed" means no frame in the clip was confident enough to fit shape; the vector is the MHR default and consumers should not present body proportions as measured.
    """

    well_observed_frames = 'well_observed_frames'
    default_assumed = 'default_assumed'


class ShapeParams(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    vector: list[float] = Field(
        ...,
        description='MHR shape (beta) coefficients, frozen for the whole clip (PRD §4: shape is estimated once from well-observed frames, not per-sample).',
        min_length=1,
    )
    source: Source1 = Field(
        ...,
        description='"default_assumed" means no frame in the clip was confident enough to fit shape; the vector is the MHR default and consumers should not present body proportions as measured.',
    )


class CropRects(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    hands: list[CropRect1 | None] = Field(
        ...,
        description='Length matches `sample_times_s`. One rectangle covering both hands when both are localized closely enough to share a crop, otherwise null for that sample — v1 does not split left/right (PRD §5 MVP scope).',
    )
    feet: list[CropRect1 | None] = Field(
        ..., description='Length matches `sample_times_s`.'
    )


class PersonResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    person_id: constr(min_length=1) = Field(
        ..., description='Stable id for this person across the clip.'
    )
    track_id: conint(ge=0) = Field(
        ...,
        description="The tracker's (ByteTrack) numeric track id, kept for pipeline debugging — not guaranteed stable across re-processing.",
    )
    shape_params: ShapeParams
    root_trajectory: list[RootTrajectorySample] = Field(
        ...,
        description='Length and order exactly match the top-level `sample_times_s` array.',
    )
    samples: list[Sample] = Field(
        ...,
        description='Length and order exactly match the top-level `sample_times_s` array.',
    )
    crop_rects: CropRects


class ModelReportEntry(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    name: str = Field(
        ..., description='e.g. "sam-3d-body-dinov3", "rtmo-m", "bytetrack", "mhr".'
    )
    version: str = Field(
        ...,
        description='Weights release, git SHA, or package version pin — whichever the PRD §3 pipeline table pins for that stage.',
    )
    license: str = Field(
        ...,
        description='e.g. "SAM License", "Apache-2.0", "MIT". Free text, not an SPDX enum, because the SAM License is not SPDX-listed (PRD §2 G2).',
    )
    license_flags: list[str] = Field(
        ...,
        description='Free-text compliance flags relevant to this specific job/output, e.g. "itar-military-use-prohibited", "citation-required-for-research-publication". Empty array for permissively-licensed stages.',
    )


class MeasuredPerformance(BaseModel):
    """
    null only if this job ran in an environment where per-job measurement genuinely wasn't wired up yet; every job in and after Milestone A (PRD §8) should populate this.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    fps: PositiveFloat = Field(
        ...,
        description='Measured end-to-end throughput for THIS clip, automatic detection (never an oracle-box number, PRD §2 G7/CONCEPTS.md).',
    )
    peak_vram_mb: PositiveFloat
    cost_usd: confloat(ge=0.0) = Field(
        ...,
        description="Measured, not a vendor-quoted rate card figure — PRD ground rule: measure, don't trust published numbers.",
    )


class ModelReport(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    pipeline_git_sha: constr(min_length=1) = Field(
        ...,
        description='Commit SHA of the pipeline fork (PRD §3 pins commit 808b53c as the starting point; this is the SHA actually used for this job, which may move forward).',
    )
    models: list[ModelReportEntry] = Field(
        ...,
        description='One entry per model/weights stage actually invoked for this job (PRD §3 pipeline table).',
        min_length=1,
    )
    measured_performance: MeasuredPerformance | None = Field(
        ...,
        description="null only if this job ran in an environment where per-job measurement genuinely wasn't wired up yet; every job in and after Milestone A (PRD §8) should populate this.",
    )


class MotionResult(BaseModel):
    """
    The frozen, versioned output of a completed stepwise motion job: one person (MVP) tracked and lifted to 3D from one monocular clip. This document describes a FINISHED job only — queued/processing/failed state lives in the separate job-status.schema.json contract, never here. Units: meters, seconds, radians-free (all rotations are quaternions). Axes: glTF/three.js convention — right-handed, +Y up, matrices column-major — chosen because the animation clip this document points to is consumed by GLTFLoader/AnimationMixer downstream. Open-decision note (OPEN-DECISIONS.md E3): this contract does not prescribe HOW the GLB hides a suppressed body region (separate meshes vs. vertex masks vs. blend shapes) — that is an exporter/renderer technique choice. It only guarantees per-joint `visibility` and `provenance` are available so any technique can consume them, and that a suppressed wrist implies its hand region should render as absent/uncertain (conservative region suppression, per PRD §4).
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['1.0.0'] = Field(
        ...,
        description='MotionResult contract version. Bump on any breaking field change; consumers should refuse to parse an unrecognized version rather than guess.',
    )
    job_id: constr(min_length=1) = Field(
        ...,
        description='Immutable id of the job that produced this result. Ties back to the separate job-status contract. Not a URL, not expiring.',
    )
    source_video: SourceVideo
    sample_times_s: list[confloat(ge=0.0)] = Field(
        ...,
        description='THE MOST IMPORTANT FIELD. One timestamp per sample slot, in seconds on the normalized video timeline (t=0 is the first frame of source_video after normalization), strictly increasing. Length N is authoritative for every other per-sample array in this document (persons[i].samples, persons[i].root_trajectory, persons[i].crop_rects.*) — they all have exactly N entries, in the same order. A slot exists here even for a sample that was fully suppressed (see Provenance) — do NOT reconstruct timestamps from `array index * (1 / fps_nominal)`; frame drops, variable-rate ingest, and suppression all break that arithmetic. This field is what playback, seeking, and visibility re-entry are computed against.',
        min_length=1,
    )
    camera: Camera
    grounding: Grounding
    accent_color: AccentColor
    joint_hierarchy: JointHierarchy
    animation: AnimationRef
    persons: list[PersonResult] = Field(
        ...,
        description='MVP always has exactly one entry (PRD §5: one dancer). Array shape kept for the multi-dancer case named as a future direction in PRD §9 — do not special-case length 1 in consumers.',
        min_length=1,
    )
    model_report: ModelReport
