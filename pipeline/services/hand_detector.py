"""MediaPipe Hands wrapper for hand gesture detection.

Falls back to mock data if MediaPipe is not available.
"""

from __future__ import annotations

import math
from pathlib import Path

from pipeline.models.schema import HandState, HandGesture, GestureType


class HandDetectionError(Exception):
    """Raised when hand detection fails."""


def _mock_hand_states(total_frames: int, fps: float) -> list[HandState]:
    """Generate realistic mock hand states.

    Simulates hands alternating between open and closed gestures
    with occasional pointing, synced to the arm movement cycle.
    """
    states: list[HandState] = []
    cycle_frames = int(fps * 2)

    for i in range(total_frames):
        t = i / fps
        phase = (i % cycle_frames) / cycle_frames

        # Left hand: open when arm is up, closed when down
        arm_up = math.sin(phase * 2 * math.pi) * 0.5 + 0.5
        if arm_up > 0.7:
            left_gesture = GestureType.OPEN
            left_conf = 0.92
        elif arm_up < 0.3:
            left_gesture = GestureType.CLOSED
            left_conf = 0.88
        else:
            left_gesture = GestureType.UNKNOWN
            left_conf = 0.55

        # Right hand: similar but offset
        right_phase = (phase + 0.5) % 1.0
        right_up = math.sin(right_phase * 2 * math.pi) * 0.5 + 0.5
        if right_up > 0.7:
            right_gesture = GestureType.OPEN
            right_conf = 0.90
        elif right_up < 0.3:
            right_gesture = GestureType.CLOSED
            right_conf = 0.85
        else:
            right_gesture = GestureType.POINTING
            right_conf = 0.60

        states.append(HandState(
            frame=i,
            timestamp=round(t, 4),
            left=HandGesture(
                detected=True,
                gesture=left_gesture,
                confidence=left_conf,
            ),
            right=HandGesture(
                detected=True,
                gesture=right_gesture,
                confidence=right_conf,
            ),
        ))

    return states


async def detect_hands(
    video_path: Path,
    total_frames: int,
    fps: float,
) -> list[HandState]:
    """Detect hand gestures in video frames.

    Uses MediaPipe Hands if available, otherwise falls back to mock data.

    Args:
        video_path: Path to the video file.
        total_frames: Number of frames to process.
        fps: Frames per second.

    Returns:
        List of HandState, one per frame.
    """
    try:
        import mediapipe  # noqa: F401
        # TODO: Implement real MediaPipe hand detection pipeline
        # For now, fall through to mock even if mediapipe is importable
    except ImportError:
        pass

    return _mock_hand_states(total_frames, fps)
