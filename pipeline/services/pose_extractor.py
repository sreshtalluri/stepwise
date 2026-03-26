"""3D body pose extraction using MediaPipe Pose (Tasks API) or mock fallback.

Set environment variable USE_REAL_POSE=true to use MediaPipe Pose.
Otherwise, the mock implementation generates realistic fake pose data.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from pipeline.models.schema import FramePose, Joint3D


# 24 SMPL joint names in standard order
SMPL_JOINT_NAMES = [
    "pelvis", "left_hip", "right_hip", "spine1",
    "left_knee", "right_knee", "spine2",
    "left_ankle", "right_ankle", "spine3",
    "left_foot", "right_foot", "neck",
    "left_collar", "right_collar", "head",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hand", "right_hand",
]

# Base T-pose positions for SMPL skeleton (approximate, in meters)
_BASE_POSITIONS: dict[str, tuple[float, float, float]] = {
    "pelvis":          (0.0,   0.95, 0.0),
    "left_hip":        (0.09,  0.90, 0.0),
    "right_hip":       (-0.09, 0.90, 0.0),
    "spine1":          (0.0,   1.05, 0.0),
    "left_knee":       (0.09,  0.50, 0.0),
    "right_knee":      (-0.09, 0.50, 0.0),
    "spine2":          (0.0,   1.15, 0.0),
    "left_ankle":      (0.09,  0.08, 0.0),
    "right_ankle":     (-0.09, 0.08, 0.0),
    "spine3":          (0.0,   1.25, 0.0),
    "left_foot":       (0.09,  0.02, 0.05),
    "right_foot":      (-0.09, 0.02, 0.05),
    "neck":            (0.0,   1.45, 0.0),
    "left_collar":     (0.05,  1.40, 0.0),
    "right_collar":    (-0.05, 1.40, 0.0),
    "head":            (0.0,   1.60, 0.0),
    "left_shoulder":   (0.18,  1.40, 0.0),
    "right_shoulder":  (-0.18, 1.40, 0.0),
    "left_elbow":      (0.40,  1.40, 0.0),
    "right_elbow":     (-0.40, 1.40, 0.0),
    "left_wrist":      (0.60,  1.40, 0.0),
    "right_wrist":     (-0.60, 1.40, 0.0),
    "left_hand":       (0.65,  1.40, 0.0),
    "right_hand":      (-0.65, 1.40, 0.0),
}

# ---------------------------------------------------------------------------
# MediaPipe landmark index -> SMPL joint mapping
# MediaPipe Pose Landmarker has 33 landmarks; we map to 24 SMPL joints.
# For joints without a direct MediaPipe equivalent, we interpolate.
# ---------------------------------------------------------------------------

# MediaPipe Pose landmark indices
_MP_NOSE = 0
_MP_LEFT_SHOULDER = 11
_MP_RIGHT_SHOULDER = 12
_MP_LEFT_ELBOW = 13
_MP_RIGHT_ELBOW = 14
_MP_LEFT_WRIST = 15
_MP_RIGHT_WRIST = 16
_MP_LEFT_PINKY = 17
_MP_RIGHT_PINKY = 18
_MP_LEFT_INDEX = 19
_MP_RIGHT_INDEX = 20
_MP_LEFT_HIP = 23
_MP_RIGHT_HIP = 24
_MP_LEFT_KNEE = 25
_MP_RIGHT_KNEE = 26
_MP_LEFT_ANKLE = 27
_MP_RIGHT_ANKLE = 28
_MP_LEFT_HEEL = 29
_MP_RIGHT_HEEL = 30
_MP_LEFT_FOOT_INDEX = 31
_MP_RIGHT_FOOT_INDEX = 32

# Scale factor for image-space landmarks (normalized [0,1] -> meters)
_SCALE = 1.8


def _midpoint(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def _lerp(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _landmarks_to_smpl_joints(landmarks, world: bool = False) -> list[Joint3D]:
    """Convert MediaPipe Pose landmarks to 24 SMPL joints.

    Args:
        landmarks: List of landmark objects with x, y, z attributes.
        world: If True, landmarks are in world coordinates (meters, hip-centered).
               If False, landmarks are in image-normalized coordinates.

    Returns:
        List of 24 Joint3D in SMPL order.
    """
    def lm(idx: int) -> tuple[float, float, float]:
        l = landmarks[idx]
        if world:
            # World landmarks: x=right, y=down, z=toward camera
            # Convert to: x=right, y=up, z=forward
            return (l.x, -l.y, -l.z)
        else:
            # Image landmarks: x,y in [0,1], z is depth
            return (
                (l.x - 0.5) * _SCALE,
                (1.0 - l.y) * _SCALE,
                -l.z * _SCALE,
            )

    # Direct mappings
    left_shoulder = lm(_MP_LEFT_SHOULDER)
    right_shoulder = lm(_MP_RIGHT_SHOULDER)
    left_elbow = lm(_MP_LEFT_ELBOW)
    right_elbow = lm(_MP_RIGHT_ELBOW)
    left_wrist = lm(_MP_LEFT_WRIST)
    right_wrist = lm(_MP_RIGHT_WRIST)
    left_hip = lm(_MP_LEFT_HIP)
    right_hip = lm(_MP_RIGHT_HIP)
    left_knee = lm(_MP_LEFT_KNEE)
    right_knee = lm(_MP_RIGHT_KNEE)
    left_ankle = lm(_MP_LEFT_ANKLE)
    right_ankle = lm(_MP_RIGHT_ANKLE)
    nose = lm(_MP_NOSE)

    # Foot: midpoint of heel and foot index
    left_foot = _midpoint(lm(_MP_LEFT_HEEL), lm(_MP_LEFT_FOOT_INDEX))
    right_foot = _midpoint(lm(_MP_RIGHT_HEEL), lm(_MP_RIGHT_FOOT_INDEX))

    # Hands: midpoint of pinky and index finger tip
    left_hand = _midpoint(lm(_MP_LEFT_PINKY), lm(_MP_LEFT_INDEX))
    right_hand = _midpoint(lm(_MP_RIGHT_PINKY), lm(_MP_RIGHT_INDEX))

    # Derived joints (interpolated)
    pelvis = _midpoint(left_hip, right_hip)
    neck = _midpoint(left_shoulder, right_shoulder)
    head = (nose[0], nose[1] + 0.08, nose[2])

    # Spine: interpolate between pelvis and neck
    spine1 = _lerp(pelvis, neck, 0.25)
    spine2 = _lerp(pelvis, neck, 0.50)
    spine3 = _lerp(pelvis, neck, 0.75)

    # Collar: between neck and shoulder
    left_collar = _midpoint(neck, left_shoulder)
    right_collar = _midpoint(neck, right_shoulder)

    joint_positions: dict[str, tuple[float, float, float]] = {
        "pelvis": pelvis,
        "left_hip": left_hip,
        "right_hip": right_hip,
        "spine1": spine1,
        "left_knee": left_knee,
        "right_knee": right_knee,
        "spine2": spine2,
        "left_ankle": left_ankle,
        "right_ankle": right_ankle,
        "spine3": spine3,
        "left_foot": left_foot,
        "right_foot": right_foot,
        "neck": neck,
        "left_collar": left_collar,
        "right_collar": right_collar,
        "head": head,
        "left_shoulder": left_shoulder,
        "right_shoulder": right_shoulder,
        "left_elbow": left_elbow,
        "right_elbow": right_elbow,
        "left_wrist": left_wrist,
        "right_wrist": right_wrist,
        "left_hand": left_hand,
        "right_hand": right_hand,
    }

    joints = []
    for name in SMPL_JOINT_NAMES:
        x, y, z = joint_positions[name]
        joints.append(Joint3D(name=name, x=round(x, 4), y=round(y, 4), z=round(z, 4)))
    return joints


def _default_tpose_joints() -> list[Joint3D]:
    """Return T-pose joints as a default when no pose is detected."""
    return [
        Joint3D(name=name, x=round(p[0], 4), y=round(p[1], 4), z=round(p[2], 4))
        for name, p in ((n, _BASE_POSITIONS[n]) for n in SMPL_JOINT_NAMES)
    ]


def _find_model_path() -> str:
    """Locate the MediaPipe Pose Landmarker model file.

    Searches in order:
    1. /models/mediapipe/pose_landmarker_heavy.task  (Modal container)
    2. pipeline/models/mediapipe/pose_landmarker_heavy.task  (local dev)
    3. Relative to this file
    """
    candidates = [
        "/models/mediapipe/pose_landmarker_heavy.task",
        str(Path(__file__).parent.parent / "models" / "mediapipe" / "pose_landmarker_heavy.task"),
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise FileNotFoundError(
        "MediaPipe Pose Landmarker model not found. "
        "Download it: curl -L -o pipeline/models/mediapipe/pose_landmarker_heavy.task "
        "'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task'"
    )


def _extract_poses_mediapipe(video_path: str, total_frames: int, fps: float) -> list[FramePose]:
    """Extract 3D poses from video using MediaPipe Pose Landmarker (Tasks API).

    Processes every frame and maps MediaPipe's 33 landmarks to 24 SMPL joints.
    Uses world landmarks when available for better 3D accuracy.
    If a frame has no detected pose, the previous frame's pose is carried forward.
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )

    model_path = _find_model_path()

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_segmentation_masks=False,
    )

    frames: list[FramePose] = []
    last_joints: list[Joint3D] | None = None
    last_joints_3d: list[Joint3D] | None = None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    with PoseLandmarker.create_from_options(options) as landmarker:
        frame_idx = 0
        while frame_idx < total_frames:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert BGR to RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Timestamp in milliseconds (must be monotonically increasing)
            timestamp_ms = int(frame_idx * 1000 / fps)

            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                # Image-space joints: map directly to video pixels (for ghost overlay)
                joints = _landmarks_to_smpl_joints(result.pose_landmarks[0], world=False)

                # World-blended joints: correct 3D proportions (for perspective views)
                joints_3d = None
                if result.pose_world_landmarks and len(result.pose_world_landmarks) > 0:
                    img_lms = result.pose_landmarks[0]
                    world_lms = result.pose_world_landmarks[0]
                    img_pelvis_x = (img_lms[_MP_LEFT_HIP].x + img_lms[_MP_RIGHT_HIP].x) / 2
                    img_pelvis_y = (img_lms[_MP_LEFT_HIP].y + img_lms[_MP_RIGHT_HIP].y) / 2
                    global_x = (img_pelvis_x - 0.5) * _SCALE
                    global_y = (1.0 - img_pelvis_y) * _SCALE
                    world_joints = _landmarks_to_smpl_joints(world_lms, world=True)
                    joints_3d = [
                        Joint3D(
                            name=wj.name,
                            x=round(wj.x + global_x, 4),
                            y=round(wj.y + global_y, 4),
                            z=round(wj.z, 4),
                        )
                        for wj in world_joints
                    ]

                last_joints = joints
                last_joints_3d = joints_3d
            elif last_joints is not None:
                joints = last_joints
                joints_3d = last_joints_3d
            else:
                joints = _default_tpose_joints()
                joints_3d = None
                last_joints = joints
                last_joints_3d = None

            timestamp = round(frame_idx / fps, 4)
            frames.append(FramePose(frame=frame_idx, timestamp=timestamp, joints=joints, joints_3d=joints_3d))
            frame_idx += 1

    cap.release()

    # Pad if video had fewer frames than expected
    while len(frames) < total_frames:
        if last_joints is None:
            last_joints = _default_tpose_joints()
        timestamp = round(len(frames) / fps, 4)
        frames.append(FramePose(frame=len(frames), timestamp=timestamp, joints=last_joints, joints_3d=last_joints_3d))

    return frames


# ---------------------------------------------------------------------------
# Mock implementation (fallback)
# ---------------------------------------------------------------------------


def _generate_mock_movement(
    total_frames: int,
    fps: float,
) -> list[FramePose]:
    """Generate a realistic mock movement: arms raising/lowering with body sway.

    The animation cycles through:
    - Arms raise from sides to overhead and back (2-second cycle)
    - Slight body sway side-to-side
    - Knees bend slightly on the beat
    """
    frames: list[FramePose] = []
    cycle_frames = int(fps * 2)  # 2-second cycle

    for i in range(total_frames):
        t = i / fps  # time in seconds
        phase = (i % cycle_frames) / cycle_frames  # 0..1 over cycle
        arm_angle = math.sin(phase * 2 * math.pi) * 0.5 + 0.5  # 0..1
        sway = math.sin(phase * 4 * math.pi) * 0.03  # lateral sway
        knee_bend = max(0, math.sin(phase * 4 * math.pi)) * 0.05

        joints: list[Joint3D] = []
        for name in SMPL_JOINT_NAMES:
            bx, by, bz = _BASE_POSITIONS[name]
            x, y, z = bx, by, bz

            # Apply lateral sway to upper body
            if "spine" in name or "neck" in name or "head" in name or "shoulder" in name or "collar" in name:
                x += sway

            # Animate arms: raise from sides to overhead
            if name in ("left_shoulder", "left_elbow", "left_wrist", "left_hand"):
                angle = arm_angle * math.pi  # 0 to pi
                dist_from_shoulder = abs(bx - 0.18) + abs(by - 1.40)
                if dist_from_shoulder < 0.01:
                    pass  # shoulder stays
                else:
                    # Rotate arm upward
                    rel_x = bx - 0.18
                    rel_y = by - 1.40
                    length = math.sqrt(rel_x**2 + rel_y**2)
                    base_angle = math.atan2(rel_y, rel_x)
                    new_angle = base_angle + angle
                    x = 0.18 + length * math.cos(new_angle) + sway
                    y = 1.40 + length * math.sin(new_angle)

            if name in ("right_shoulder", "right_elbow", "right_wrist", "right_hand"):
                angle = arm_angle * math.pi
                dist_from_shoulder = abs(bx - (-0.18)) + abs(by - 1.40)
                if dist_from_shoulder < 0.01:
                    pass
                else:
                    rel_x = bx - (-0.18)
                    rel_y = by - 1.40
                    length = math.sqrt(rel_x**2 + rel_y**2)
                    base_angle = math.atan2(rel_y, rel_x)
                    new_angle = base_angle + (math.pi - angle)
                    x = -0.18 + length * math.cos(new_angle) + sway
                    y = 1.40 + length * math.sin(new_angle)

            # Knee bend
            if "knee" in name:
                y -= knee_bend
                z += knee_bend * 0.5
            if "ankle" in name or "foot" in name:
                y -= knee_bend * 0.3

            joints.append(Joint3D(name=name, x=round(x, 4), y=round(y, 4), z=round(z, 4)))

        frames.append(FramePose(
            frame=i,
            timestamp=round(t, 4),
            joints=joints,
        ))

    return frames


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_poses(
    video_path: Path,
    total_frames: int,
    fps: float,
) -> list[FramePose]:
    """Extract 3D body poses from video.

    Uses MediaPipe Pose Landmarker when USE_REAL_POSE=true, otherwise returns mock data.

    Args:
        video_path: Path to the video file.
        total_frames: Number of frames to generate poses for.
        fps: Frames per second of the video.

    Returns:
        List of FramePose, one per frame, each with 24 SMPL joints.
    """
    use_real = os.environ.get("USE_REAL_POSE", "false").lower() in ("true", "1", "yes")

    if use_real:
        import asyncio
        # Run in executor since MediaPipe + OpenCV are blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _extract_poses_mediapipe, str(video_path), total_frames, fps
        )

    return _generate_mock_movement(total_frames, fps)
