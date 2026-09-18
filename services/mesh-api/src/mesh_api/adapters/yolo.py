from __future__ import annotations

from mesh_api.adapters.base import Detection
from mesh_api.models import LicenseFlag, ModelDescriptor


class YoloDetectorUnavailable(RuntimeError):
    pass


class UltralyticsYoloPersonDetector:
    """Production-oriented YOLO person detector scaffold.

    The adapter is not imported by default because Ultralytics may not be
    installed and its AGPL/Enterprise licensing must be reviewed for the target
    deployment. This class documents and enforces the adapter boundary.
    """

    descriptor = ModelDescriptor(name="Ultralytics YOLO Person Detector", version="scaffold", adapter="ultralytics-yolo")
    license_flags = [
        LicenseFlag(
            component="ultralytics",
            license="AGPL-3.0-or-enterprise",
            commercial_use="restricted",
            note="Closed/proprietary deployment requires AGPL compliance or an Ultralytics Enterprise License.",
        )
    ]

    def __init__(self, model_name: str = "yolo11n.pt", confidence: float = 0.35) -> None:
        self.model_name = model_name
        self.confidence = confidence
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:  # pragma: no cover - optional production dependency
            raise YoloDetectorUnavailable("Install ultralytics in the GPU worker image to enable this adapter") from exc
        self._model = YOLO(model_name)

    def detect(self, source_url: str, target_fps: int) -> list[list[Detection]]:  # pragma: no cover - optional production dependency
        results = self._model.track(source=source_url, conf=self.confidence, classes=[0], stream=True, persist=True)
        frames: list[list[Detection]] = []
        for frame_index, result in enumerate(results):
            frame: list[Detection] = []
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                frames.append(frame)
                continue
            for box_index, xyxy in enumerate(boxes.xyxy.tolist()):
                x1, y1, x2, y2 = xyxy
                width = max(1, getattr(result.orig_img, "shape", [1, 1])[1])
                height = max(1, getattr(result.orig_img, "shape", [1, 1])[0])
                confidence = float(boxes.conf[box_index]) if boxes.conf is not None else 0.0
                track_id = str(int(boxes.id[box_index])) if boxes.id is not None else str(box_index)
                frame.append(
                    Detection(
                        frame_index=frame_index,
                        timestamp_seconds=frame_index / target_fps,
                        bbox=[x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height],
                        confidence=confidence,
                        label_hint=track_id,
                    )
                )
            frames.append(frame)
        return frames
