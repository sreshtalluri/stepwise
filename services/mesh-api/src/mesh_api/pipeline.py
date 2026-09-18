from __future__ import annotations

import time
from dataclasses import dataclass
from mesh_api.adapters.base import PersonDetector, PersonTracker, MeshRecoverer, Track, VideoIngestor, VideoProbe
from mesh_api.adapters.mock import JOINTS, keypoints_for_detection, pose_params
from mesh_api.config import Settings
from mesh_api.models import (
    Analysis,
    AssetManifest,
    Frame,
    JointPose,
    MeshResultV1,
    ModelReport,
    Person,
    PersonFrame,
    Transform,
    VideoMetadata,
)


class NoPeopleFoundError(RuntimeError):
    pass


class VideoTooLongError(RuntimeError):
    pass


@dataclass(frozen=True)
class PipelineAdapters:
    ingestor: VideoIngestor
    detector: PersonDetector
    tracker: PersonTracker
    mesh_recoverer: MeshRecoverer



def run_pipeline(source_url: str, settings: Settings, adapters: PipelineAdapters) -> MeshResultV1:
    started = time.perf_counter()
    video_probe = adapters.ingestor.probe(source_url)
    if video_probe.duration_seconds > settings.max_video_seconds:
        raise VideoTooLongError(f"Video is too long ({video_probe.duration_seconds:.0f}s). Max is {settings.max_video_seconds}s.")

    detections_by_frame = adapters.detector.detect(video_probe.local_ref, settings.target_mesh_fps)
    if not any(detections_by_frame):
        raise NoPeopleFoundError("No people detected in the source video.")

    tracks = adapters.tracker.track(detections_by_frame)
    track_by_id = {track.track_id: track for track in tracks}
    people = _recover_people(tracks, adapters.mesh_recoverer)
    frames = _build_frames(detections_by_frame, track_by_id, settings.target_mesh_fps)
    warnings = [person.error for person in people if person.error]
    if warnings:
        warnings = [f"Partial result: {warning}" for warning in warnings]
    runtime_ms = max(1, int((time.perf_counter() - started) * 1000))

    return MeshResultV1(
        video=VideoMetadata(
            source_url=video_probe.source_url,
            playback_url=video_probe.playback_url,
            duration_seconds=video_probe.duration_seconds,
            fps=video_probe.fps,
            dimensions={"width": video_probe.width, "height": video_probe.height},
        ),
        people=people,
        frames=frames,
        analysis=_analyze(people, frames),
        assets=AssetManifest(
            mesh_asset_urls=[{"track_id": person.track_id, "url": f"https://assets.stepwise.local/signed/{person.track_id}.mesh.json", "content_type": "application/json"} for person in people if person.mesh_asset],
            glb_url="https://assets.stepwise.local/signed/stepwise-result.glb",
            debug_overlay_urls=["https://assets.stepwise.local/signed/debug-overlay.mp4"],
        ),
        model_report=ModelReport(
            detector=adapters.detector.descriptor,
            tracker=adapters.tracker.descriptor,
            mesh=adapters.mesh_recoverer.descriptor,
            runtime_ms=runtime_ms,
            warnings=warnings,
            license_flags=adapters.detector.license_flags + adapters.tracker.license_flags + adapters.mesh_recoverer.license_flags,
        ),
    )


def _recover_people(tracks: list[Track], mesh_recoverer: MeshRecoverer) -> list[Person]:
    colors = ["#00d4ff", "#44ff88", "#ffdd44", "#ff8844"]
    people: list[Person] = []
    longest = max((len(track.detections) for track in tracks), default=1)
    for index, track in enumerate(tracks):
        mesh = None
        error = None
        try:
            mesh = mesh_recoverer.recover(track)
        except Exception as exc:  # partial-result policy is explicit in v1
            error = str(exc)
        frames = [d.frame_index for d in track.detections]
        coverage = len(track.detections) / longest
        center_bonus = 1 - min(abs(_average_center_x(track) - 0.5) * 1.4, 0.5)
        people.append(
            Person(
                track_id=track.track_id,
                color=colors[index % len(colors)],
                confidence=round(track.confidence, 3),
                visible_frame_ranges=[[min(frames), max(frames)]],
                primary_dancer_score=round(min(1, coverage * center_bonus), 3),
                mesh_asset=mesh,
                error=error,
            )
        )
    return people


def _average_center_x(track: Track) -> float:
    return sum(d.bbox[0] + d.bbox[2] / 2 for d in track.detections) / len(track.detections)


def _build_frames(detections_by_frame, track_by_id: dict[str, Track], fps: int) -> list[Frame]:
    frames: list[Frame] = []
    for frame_index, detections in enumerate(detections_by_frame):
        people: list[PersonFrame] = []
        for detection in detections:
            track_id = f"person-{detection.label_hint}"
            x = round(detection.bbox[0] - 0.5, 3)
            joints = _animated_joints(frame_index, track_id, x, detection.confidence)
            people.append(
                PersonFrame(
                    track_id=track_id,
                    bbox=detection.bbox,
                    keypoints_2d=keypoints_for_detection(detection),
                    joints_3d=joints,
                    pose_params=pose_params(frame_index, track_id),
                    global_transform=Transform(translation=[x, 0, 0], rotation=[0, 0, 0, 1], scale=[1, 1, 1]),
                    visibility=detection.confidence,
                    tracking_confidence=track_by_id[track_id].confidence,
                )
            )
        frames.append(Frame(frame_index=frame_index, timestamp_seconds=round(frame_index / fps, 3), people=people))
    return frames


def _animated_joints(frame_index: int, track_id: str, x: float, confidence: float) -> list[JointPose]:
    phase = frame_index * 0.55 + (0.8 if track_id.endswith("beta") else 0)
    arm_lift = 0.18 * (1 + __import__("math").sin(phase)) / 2
    arm_swing = 0.12 * __import__("math").sin(phase * 1.3)
    leg_swing = 0.08 * __import__("math").sin(phase + 0.9)
    bounce = 0.025 * __import__("math").sin(phase * 2)
    offsets = {
        "hips": [0, bounce, 0],
        "spine": [0, bounce, 0],
        "chest": [0, bounce + 0.02 * __import__("math").sin(phase), 0],
        "neck": [0, bounce + 0.03 * __import__("math").sin(phase), 0],
        "head": [0.015 * __import__("math").sin(phase), bounce + 0.03 * __import__("math").sin(phase), 0],
        "left_upper_arm": [-arm_swing * 0.25, arm_lift * 0.35, 0.02],
        "left_lower_arm": [-arm_swing * 0.65, arm_lift, 0.04],
        "left_hand": [-arm_swing, arm_lift * 1.35, 0.06],
        "right_upper_arm": [arm_swing * 0.25, 0.16 - arm_lift * 0.25, -0.02],
        "right_lower_arm": [arm_swing * 0.65, 0.16 - arm_lift * 0.8, -0.04],
        "right_hand": [arm_swing, 0.16 - arm_lift, -0.06],
        "left_thigh": [0.02 * __import__("math").sin(phase), 0, 0],
        "left_shin": [leg_swing * 0.6, 0.02 * abs(__import__("math").sin(phase)), 0],
        "left_foot": [leg_swing, 0.03 * abs(__import__("math").sin(phase)), 0.05 * __import__("math").cos(phase)],
        "right_thigh": [-0.02 * __import__("math").sin(phase), 0, 0],
        "right_shin": [-leg_swing * 0.6, 0.02 * abs(__import__("math").cos(phase)), 0],
        "right_foot": [-leg_swing, 0.03 * abs(__import__("math").cos(phase)), -0.05 * __import__("math").sin(phase)],
    }
    joints: list[JointPose] = []
    for joint in JOINTS:
        offset = offsets.get(joint.name, [0, 0, 0])
        position = [round(joint.rest_position[0] + x + offset[0], 3), round(joint.rest_position[1] + offset[1], 3), round(joint.rest_position[2] + offset[2], 3)]
        angle = (abs(offset[0]) + abs(offset[1]) + abs(offset[2])) * 0.8
        rotation = [round(angle, 3), 0, 0, round(max(0.0, 1 - angle * 0.1), 3)] if angle else [0, 0, 0, 1]
        joints.append(JointPose(name=joint.name, position=position, rotation=rotation, confidence=confidence))
    return joints


def _analyze(people: list[Person], frames: list[Frame]) -> Analysis:
    timeline = [{"timestamp_seconds": frame.timestamp_seconds, "score": round(0.35 + 0.35 * (frame.frame_index % 4) / 3, 3)} for frame in frames]
    foot_contacts = [
        {"track_id": person.track_id, "foot": foot, "timestamp_seconds": frame.timestamp_seconds, "contact": "flat" if frame.frame_index % 2 == 0 else "toe", "confidence": 0.88}
        for person in people
        for foot in ("left", "right")
        for frame in frames[::3]
    ]
    path_trails = []
    for person in people:
        for joint_name in ("left_hand", "right_hand", "left_foot", "right_foot"):
            points = []
            for frame in frames:
                pose = next((p for p in frame.people if p.track_id == person.track_id), None)
                if pose:
                    joint = next(j for j in pose.joints_3d if j.name == joint_name)
                    points.append({"timestamp_seconds": frame.timestamp_seconds, "position": joint.position})
            path_trails.append({"track_id": person.track_id, "joint_name": joint_name, "points": points})
    return Analysis(
        beats=[{"timestamp_seconds": 0, "strength": 1}, {"timestamp_seconds": 0.5, "strength": 0.65}, {"timestamp_seconds": 1.0, "strength": 0.82}],
        difficulty={"overall_score": 0.58, "timeline": timeline, "body_parts": {"arms": 0.72, "legs": 0.54, "core": 0.38}},
        foot_contacts=foot_contacts,
        path_trails=path_trails,
        step_segments=[{"label": "opening groove", "start_seconds": 0, "end_seconds": 0.8, "difficulty": 0.45, "primary_body_part": "core"}, {"label": "cross-body hit", "start_seconds": 0.8, "end_seconds": 1.6, "difficulty": 0.7, "primary_body_part": "arms"}],
    )
