from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DETECTING = "detecting"
    TRACKING = "tracking"
    MESHING = "meshing"
    SKINNING = "skinning"
    SMOOTHING = "smoothing"
    ANALYZING = "analyzing"
    PACKAGING = "packaging"
    COMPLETE = "complete"
    FAILED = "failed"


class JobCreate(BaseModel):
    source_url: str | None = None
    upload_ref: str | None = None

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("source_url must be an http(s) URL")
        return value

    @field_validator("upload_ref")
    @classmethod
    def validate_upload_ref(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("storage://"):
            raise ValueError("upload_ref must be a storage:// reference")
        return value


class UploadPresignCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(default="video/mp4")
    content_length: int = Field(gt=0)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        if not (value.startswith("video/") or value == "application/octet-stream"):
            raise ValueError("content_type must be video/* or application/octet-stream")
        return value


class UploadPresignResponse(BaseModel):
    method: Literal["PUT"] = "PUT"
    upload_url: str
    upload_ref: str
    object_key: str
    headers: dict[str, str]
    expires_in_seconds: int


class JobStatus(BaseModel):
    job_id: str
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    people_detected: int = 0
    error: str | None = None


class ModelDescriptor(BaseModel):
    name: str
    version: str
    adapter: str
    enabled: bool = True


class LicenseFlag(BaseModel):
    component: str
    license: str
    commercial_use: Literal["allowed", "restricted", "unknown"]
    note: str


class VideoMetadata(BaseModel):
    source_url: str
    playback_url: str
    duration_seconds: float
    fps: float
    dimensions: dict[str, int]


class SkinWeight(BaseModel):
    joints: list[int]
    weights: list[float]


class JointDefinition(BaseModel):
    name: str
    parent_index: int | None
    rest_position: list[float]


class ShapeParameters(BaseModel):
    height_m: float
    shoulder_width_m: float
    hip_width_m: float
    body_shape_coefficients: list[float]


class MeshAsset(BaseModel):
    asset_id: str
    format: Literal["inline-rest-mesh-v1"] = "inline-rest-mesh-v1"
    vertices: list[list[float]]
    normals: list[list[float]]
    faces: list[list[int]]
    skin_weights: list[SkinWeight]
    joint_hierarchy: list[JointDefinition]
    inverse_bind_matrices: list[list[float]]
    shape_parameters: ShapeParameters
    source_model: str


class Person(BaseModel):
    track_id: str
    color: str
    confidence: float = Field(ge=0, le=1)
    visible_frame_ranges: list[list[int]]
    primary_dancer_score: float = Field(ge=0, le=1)
    mesh_asset: MeshAsset | None
    error: str | None = None


class Keypoint2D(BaseModel):
    name: str
    position: list[float]
    confidence: float = Field(ge=0, le=1)


class JointPose(BaseModel):
    name: str
    position: list[float]
    rotation: list[float]
    confidence: float = Field(ge=0, le=1)


class Transform(BaseModel):
    translation: list[float]
    rotation: list[float]
    scale: list[float]


class PersonFrame(BaseModel):
    def __getitem__(self, key: str):
        return getattr(self, key)

    track_id: str
    bbox: list[float]
    keypoints_2d: list[Keypoint2D]
    joints_3d: list[JointPose]
    pose_params: list[float]
    global_transform: Transform
    visibility: float = Field(ge=0, le=1)
    tracking_confidence: float = Field(ge=0, le=1)


class Frame(BaseModel):
    frame_index: int
    timestamp_seconds: float
    people: list[PersonFrame]


class Analysis(BaseModel):
    beats: list[dict]
    difficulty: dict
    foot_contacts: list[dict]
    path_trails: list[dict]
    step_segments: list[dict]


class AssetManifest(BaseModel):
    mesh_asset_urls: list[dict]
    glb_url: str | None = None
    debug_overlay_urls: list[str]


class ModelReport(BaseModel):
    detector: ModelDescriptor
    tracker: ModelDescriptor
    mesh: ModelDescriptor
    runtime_ms: int
    warnings: list[str]
    license_flags: list[LicenseFlag]


class MeshResultV1(BaseModel):
    schema_version: Literal["mesh-result-v1"] = "mesh-result-v1"
    video: VideoMetadata
    people: list[Person]
    frames: list[Frame]
    analysis: Analysis
    assets: AssetManifest
    model_report: ModelReport
