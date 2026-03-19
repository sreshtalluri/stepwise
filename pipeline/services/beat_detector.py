"""Beat detection using librosa."""

from __future__ import annotations

from pathlib import Path

from pipeline.models.schema import Beat


class BeatDetectionError(Exception):
    """Raised when beat detection fails."""


def _mock_beats(duration_seconds: float) -> list[Beat]:
    """Generate mock beats at ~120 BPM for testing."""
    bpm = 120.0
    interval = 60.0 / bpm
    beats: list[Beat] = []
    t = interval  # First beat after one interval
    i = 0
    while t < duration_seconds:
        # Alternate strong and weak beats (4/4 time)
        strength = 1.0 if i % 4 == 0 else (0.7 if i % 2 == 0 else 0.4)
        beats.append(Beat(timestamp=round(t, 4), strength=strength))
        t += interval
        i += 1
    return beats


async def detect_beats(
    audio_path: Path,
    duration_seconds: float,
) -> list[Beat]:
    """Detect beats in audio using librosa.

    Args:
        audio_path: Path to WAV audio file.
        duration_seconds: Duration for mock fallback.

    Returns:
        List of Beat with timestamps and strengths.
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=22050)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Compute onset strength for beat strengths
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        beats: list[Beat] = []
        for frame_idx, t in zip(beat_frames, beat_times):
            if frame_idx < len(onset_env):
                raw_strength = float(onset_env[frame_idx])
            else:
                raw_strength = 0.5

            beats.append(Beat(
                timestamp=round(float(t), 4),
                strength=round(raw_strength, 4),
            ))

        # Normalize strengths to 0-1
        if beats:
            max_str = max(b.strength for b in beats)
            if max_str > 0:
                for b in beats:
                    b.strength = round(b.strength / max_str, 4)

        return beats

    except ImportError:
        return _mock_beats(duration_seconds)
    except Exception as e:
        raise BeatDetectionError(f"Beat detection failed: {e}") from e
