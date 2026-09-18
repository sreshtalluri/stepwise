from __future__ import annotations

import math
from collections import defaultdict
from mesh_api.adapters.base import Detection, Track, VideoProbe
from mesh_api.models import JointDefinition, LicenseFlag, MeshAsset, ModelDescriptor, ShapeParameters, SkinWeight

IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
JOINTS = [
    JointDefinition(name="hips", parent_index=None, rest_position=[0, 0.92, 0]),
    JointDefinition(name="spine", parent_index=0, rest_position=[0, 1.16, 0]),
    JointDefinition(name="chest", parent_index=1, rest_position=[0, 1.34, 0]),
    JointDefinition(name="neck", parent_index=2, rest_position=[0, 1.52, 0]),
    JointDefinition(name="head", parent_index=3, rest_position=[0, 1.68, 0]),
    JointDefinition(name="left_upper_arm", parent_index=2, rest_position=[-0.34, 1.34, 0]),
    JointDefinition(name="left_lower_arm", parent_index=5, rest_position=[-0.62, 1.14, 0]),
    JointDefinition(name="left_hand", parent_index=6, rest_position=[-0.78, 0.98, 0]),
    JointDefinition(name="right_upper_arm", parent_index=2, rest_position=[0.34, 1.34, 0]),
    JointDefinition(name="right_lower_arm", parent_index=8, rest_position=[0.62, 1.14, 0]),
    JointDefinition(name="right_hand", parent_index=9, rest_position=[0.78, 0.98, 0]),
    JointDefinition(name="left_thigh", parent_index=0, rest_position=[-0.16, 0.62, 0]),
    JointDefinition(name="left_shin", parent_index=11, rest_position=[-0.17, 0.28, 0]),
    JointDefinition(name="left_foot", parent_index=12, rest_position=[-0.18, 0.04, 0.08]),
    JointDefinition(name="right_thigh", parent_index=0, rest_position=[0.16, 0.62, 0]),
    JointDefinition(name="right_shin", parent_index=14, rest_position=[0.17, 0.28, 0]),
    JointDefinition(name="right_foot", parent_index=15, rest_position=[0.18, 0.04, 0.08]),
]
JOINT_INDEX = {joint.name: index for index, joint in enumerate(JOINTS)}


class MockVideoIngestor:
    descriptor = ModelDescriptor(name="Mock Video Ingestor", version="0.1.0", adapter="mock-video-ingestor")
    license_flags: list[LicenseFlag] = []

    def probe(self, source_ref: str) -> VideoProbe:
        duration = 180.0 if "long" in source_ref else 2.0
        return VideoProbe(
            source_url=source_ref,
            playback_url=f"https://assets.stepwise.local/signed/{abs(hash(source_ref))}.mp4",
            duration_seconds=duration,
            fps=30.0,
            width=1920,
            height=1080,
            local_ref=source_ref,
        )


def inverse_bind_matrix(rest_position: list[float]) -> list[float]:
    return [1, 0, 0, -rest_position[0], 0, 1, 0, -rest_position[1], 0, 0, 1, -rest_position[2], 0, 0, 0, 1]


def _v_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _v_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _v_scale(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _v_cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _v_len(a):
    return math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)


def _v_norm(a):
    length = _v_len(a) or 1
    return [a[0] / length, a[1] / length, a[2] / length]


def _basis(start, end):
    y_axis = _v_norm(_v_sub(end, start))
    helper = [0, 0, 1] if abs(y_axis[2]) < 0.92 else [1, 0, 0]
    x_axis = _v_norm(_v_cross(helper, y_axis))
    z_axis = _v_norm(_v_cross(y_axis, x_axis))
    return x_axis, y_axis, z_axis


def _add_oriented_ellipsoid(vertices, normals, faces, weights, *, start, end, radius_x, radius_z, joint_name, rings=8, segments=14):
    base = len(vertices)
    center = _v_scale(_v_add(start, end), 0.5)
    half_len = _v_len(_v_sub(end, start)) / 2
    x_axis, y_axis, z_axis = _basis(start, end)
    joint_index = JOINT_INDEX[joint_name]
    parent_index = JOINTS[joint_index].parent_index
    skin = SkinWeight(joints=[joint_index] if parent_index is None else [joint_index, parent_index], weights=[1.0] if parent_index is None else [0.82, 0.18])

    for ring in range(rings + 1):
        phi = math.pi * ring / rings
        local_y = math.cos(phi) * half_len
        ring_scale = math.sin(phi)
        for segment in range(segments):
            theta = 2 * math.pi * segment / segments
            point = center
            point = _v_add(point, _v_scale(x_axis, math.cos(theta) * radius_x * ring_scale))
            point = _v_add(point, _v_scale(y_axis, local_y))
            point = _v_add(point, _v_scale(z_axis, math.sin(theta) * radius_z * ring_scale))
            normal = _v_norm(_v_sub(point, center))
            vertices.append([round(point[0], 4), round(point[1], 4), round(point[2], 4)])
            normals.append([round(normal[0], 4), round(normal[1], 4), round(normal[2], 4)])
            weights.append(skin)

    for ring in range(rings):
        for segment in range(segments):
            a = base + ring * segments + segment
            b = base + ring * segments + (segment + 1) % segments
            c = base + (ring + 1) * segments + segment
            d = base + (ring + 1) * segments + (segment + 1) % segments
            faces.append([a, c, b])
            faces.append([b, c, d])


class MockPersonDetector:
    descriptor = ModelDescriptor(name="Mock YOLO Person Detector", version="0.1.0", adapter="mock-yolo")
    license_flags = [
        LicenseFlag(
            component="ultralytics-yolo-adapter",
            license="AGPL-3.0-or-enterprise",
            commercial_use="restricted",
            note="YOLO-style detection is replaceable; closed-source deployments need enterprise/commercial review.",
        )
    ]

    def __init__(self, scenario: str = "two_person_crossing") -> None:
        self.scenario = scenario

    def detect(self, source_url: str, target_fps: int) -> list[list[Detection]]:
        if self.scenario == "no_people":
            return [[] for _ in range(8)]
        frames: list[list[Detection]] = []
        count = 10
        for frame_index in range(count):
            t = frame_index / target_fps
            alpha_x = 0.22 + 0.032 * frame_index
            frame = [Detection(frame_index, t, [alpha_x, 0.18, 0.22, 0.66], 0.96, "alpha")]
            if self.scenario in {"two_person_crossing", "partial_failure"}:
                label = "beta" if self.scenario == "two_person_crossing" else "gamma"
                beta_x = 0.74 - 0.03 * frame_index
                confidence = 0.9 if label == "beta" else 0.72
                if frame_index == 5 and label == "beta":
                    confidence = 0.62
                frame.append(Detection(frame_index, t, [beta_x, 0.2, 0.2, 0.64], confidence, label))
            frames.append(frame)
        return frames


class MockPersonTracker:
    descriptor = ModelDescriptor(name="Mock ByteTrack", version="0.1.0", adapter="mock-bytetrack")
    license_flags: list[LicenseFlag] = []

    def track(self, detections_by_frame: list[list[Detection]]) -> list[Track]:
        grouped: dict[str, list[Detection]] = defaultdict(list)
        for frame in detections_by_frame:
            for detection in frame:
                grouped[f"person-{detection.label_hint}"].append(detection)
        return [Track(track_id=track_id, detections=detections, confidence=sum(d.confidence for d in detections) / len(detections)) for track_id, detections in grouped.items()]


class MockMeshRecoverer:
    descriptor = ModelDescriptor(name="Mock Stylized Humanoid Body", version="0.2.0", adapter="mock-humanoid-body")
    license_flags = [
        LicenseFlag(component="sam-3d-body-mhr-candidate", license="Apache-2.0 candidate", commercial_use="allowed", note="Production adapter should verify upstream model/code license before enabling."),
        LicenseFlag(component="4d-humans-hmr2-candidate", license="research-review-required", commercial_use="unknown", note="Optional video adapter; install and license review required."),
    ]

    def __init__(self, available: bool = True) -> None:
        self.available = available

    def recover(self, track: Track) -> MeshAsset:
        if track.track_id.endswith("gamma"):
            raise RuntimeError("mesh recovery failed for this track")
        scale = 1.0 if track.track_id.endswith("alpha") else 0.93
        shoulder = 0.46 * scale
        hip = 0.32 * scale
        height = 1.72 * scale
        vertices: list[list[float]] = []
        normals: list[list[float]] = []
        faces: list[list[int]] = []
        weights: list[SkinWeight] = []

        def s(point):
            return [point[0] * scale, point[1] * scale, point[2] * scale]

        # Wii Fit / Just Dance style: smooth simplified body volumes, not realistic skin texture.
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0, 0.88, 0]), end=s([0, 1.42, 0]), radius_x=shoulder * 0.42, radius_z=0.13 * scale, joint_name="chest", rings=10, segments=16)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0, 1.43, 0]), end=s([0, 1.52, 0]), radius_x=0.08 * scale, radius_z=0.07 * scale, joint_name="neck", rings=6, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0, 1.51, 0]), end=s([0, 1.82, 0]), radius_x=0.135 * scale, radius_z=0.12 * scale, joint_name="head", rings=10, segments=16)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-shoulder / (2 * scale), 1.36, 0]), end=s([-0.63, 1.13, 0.02]), radius_x=0.065 * scale, radius_z=0.058 * scale, joint_name="left_upper_arm", rings=7, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-0.63, 1.13, 0.02]), end=s([-0.82, 0.94, 0.04]), radius_x=0.052 * scale, radius_z=0.047 * scale, joint_name="left_lower_arm", rings=7, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-0.82, 0.94, 0.04]), end=s([-0.9, 0.88, 0.05]), radius_x=0.055 * scale, radius_z=0.028 * scale, joint_name="left_hand", rings=5, segments=10)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([shoulder / (2 * scale), 1.36, 0]), end=s([0.63, 1.13, 0.02]), radius_x=0.065 * scale, radius_z=0.058 * scale, joint_name="right_upper_arm", rings=7, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0.63, 1.13, 0.02]), end=s([0.82, 0.94, 0.04]), radius_x=0.052 * scale, radius_z=0.047 * scale, joint_name="right_lower_arm", rings=7, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0.82, 0.94, 0.04]), end=s([0.9, 0.88, 0.05]), radius_x=0.055 * scale, radius_z=0.028 * scale, joint_name="right_hand", rings=5, segments=10)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-hip / (2 * scale), 0.88, 0]), end=s([-0.18, 0.43, 0.0]), radius_x=0.085 * scale, radius_z=0.075 * scale, joint_name="left_thigh", rings=8, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-0.18, 0.43, 0.0]), end=s([-0.18, 0.08, 0.02]), radius_x=0.064 * scale, radius_z=0.055 * scale, joint_name="left_shin", rings=8, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([hip / (2 * scale), 0.88, 0]), end=s([0.18, 0.43, 0.0]), radius_x=0.085 * scale, radius_z=0.075 * scale, joint_name="right_thigh", rings=8, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0.18, 0.43, 0.0]), end=s([0.18, 0.08, 0.02]), radius_x=0.064 * scale, radius_z=0.055 * scale, joint_name="right_shin", rings=8, segments=12)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([-0.19, 0.05, 0.03]), end=s([-0.19, 0.03, 0.22]), radius_x=0.07 * scale, radius_z=0.035 * scale, joint_name="left_foot", rings=5, segments=10)
        _add_oriented_ellipsoid(vertices, normals, faces, weights, start=s([0.19, 0.05, 0.03]), end=s([0.19, 0.03, 0.22]), radius_x=0.07 * scale, radius_z=0.035 * scale, joint_name="right_foot", rings=5, segments=10)

        return MeshAsset(
            asset_id=f"{track.track_id}-stylized-humanoid-rest-mesh",
            vertices=vertices,
            normals=normals,
            faces=faces,
            skin_weights=weights,
            joint_hierarchy=JOINTS,
            inverse_bind_matrices=[inverse_bind_matrix(joint.rest_position) for joint in JOINTS],
            shape_parameters=ShapeParameters(height_m=height, shoulder_width_m=shoulder, hip_width_m=hip, body_shape_coefficients=[round(scale - 1, 3), round(shoulder - 0.46, 3), 0.12]),
            source_model="mock-stylized-humanoid-body",
        )


def keypoints_for_detection(detection: Detection) -> list[dict]:
    x, y, w, h = detection.bbox
    return [
        {"name": "nose", "position": [x + w * 0.5, y + h * 0.08], "confidence": detection.confidence},
        {"name": "left_wrist", "position": [x + w * 0.15, y + h * 0.45], "confidence": max(detection.confidence - 0.05, 0)},
        {"name": "right_wrist", "position": [x + w * 0.85, y + h * 0.43], "confidence": max(detection.confidence - 0.05, 0)},
    ]


def pose_params(frame_index: int, track_id: str) -> list[float]:
    phase = frame_index * 0.2 + (0.4 if track_id.endswith("beta") else 0)
    return [round(math.sin(phase), 3), 0.1, -0.05, round(math.cos(phase) * 0.2, 3), -0.1, 0.05]
