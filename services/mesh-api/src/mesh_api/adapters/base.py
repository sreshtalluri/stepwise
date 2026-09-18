from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from mesh_api.models import MeshAsset, ModelDescriptor, LicenseFlag


@dataclass(frozen=True)
class VideoProbe:
    source_url: str
    playback_url: str
    duration_seconds: float
    fps: float
    width: int
    height: int
    local_ref: str


class VideoIngestor(Protocol):
    descriptor: ModelDescriptor
    license_flags: list[LicenseFlag]

    def probe(self, source_ref: str) -> VideoProbe: ...


@dataclass(frozen=True)
class Detection:
    frame_index: int
    timestamp_seconds: float
    bbox: list[float]
    confidence: float
    label_hint: str


@dataclass(frozen=True)
class Track:
    track_id: str
    detections: list[Detection]
    confidence: float


class PersonDetector(Protocol):
    descriptor: ModelDescriptor
    license_flags: list[LicenseFlag]

    def detect(self, source_url: str, target_fps: int) -> list[list[Detection]]: ...


class PersonTracker(Protocol):
    descriptor: ModelDescriptor
    license_flags: list[LicenseFlag]

    def track(self, detections_by_frame: list[list[Detection]]) -> list[Track]: ...


class MeshRecoverer(Protocol):
    descriptor: ModelDescriptor
    license_flags: list[LicenseFlag]
    available: bool

    def recover(self, track: Track) -> MeshAsset: ...
