"""Automatic beat/downbeat *proposal* for a clip's audio.

This is a proposal generator, not a decider (docs/OPEN-DECISIONS.md A5,
docs/DESIGN.md honesty rules). It never claims to know count 1 or the tempo —
it guesses, scores its own confidence, and flags the classic half/double-time
ambiguity so a UI (built later, not here) can let a human overrule it.
`packages/navigation/src/core.ts`'s `gridFromTaps()` is the manual path this
feeds a *starting point* for; manual tap-in always wins.

Library: librosa (ISC licence — see README for why over madmom/BeatNet).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np

_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}

# Typical dance-practice tempo band. Outside this range, half/double-time
# confusion is the most likely explanation (per A5), not a genuinely fast/slow track.
_PLAUSIBLE_BPM = (70, 180)


@dataclass
class TempoAlternate:
    """A half-time / double-time reading of the same beat grid.

    librosa's beat tracker (like any autocorrelation-based tracker) frequently
    locks onto 2x or 0.5x the tempo a human would tap. `secondsPerCount` is
    the SAME anchor grid re-hypothesized at a different subdivision — not a
    different countOneS.
    """

    label: str  # "double-time" | "half-time"
    seconds_per_count: float
    bpm: float


@dataclass
class ProposedGrid:
    """A *guess*, shaped to slot into `LessonStructure["grid"]`
    (`{countOneS, secondsPerCount, countTotal}`) — see `to_grid()`.

    Never present this as ground truth. `confidence` is the whole point of
    this module per the honesty boundary (DESIGN.md §7h): a wrong guess
    presented confidently is worse than an honest low score.
    """

    count_one_s: float
    seconds_per_count: float
    count_total: int | None  # None if no clip_duration_s was supplied
    confidence: float  # 0..1, this module's own trust in the proposal
    bpm: float
    alternates: list[TempoAlternate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_grid(self) -> dict:
        """`{countOneS, secondsPerCount, countTotal}` — exact `CountGrid`
        shape from `packages/navigation/src/core.ts`. Raises if `count_total`
        is unknown (caller never supplied the clip's end time)."""
        if self.count_total is None:
            raise ValueError("count_total is unknown; pass clip_duration_s to propose_grid()")
        return {
            "countOneS": self.count_one_s,
            "secondsPerCount": self.seconds_per_count,
            "countTotal": self.count_total,
        }

    def to_beat_proposal(self) -> dict:
        """The `MotionResult.beat_proposal` object (motion-result.schema.json).

        Unlike `to_grid()`, this carries the whole guess — confidence, tempo,
        alternates and warnings — because the contract deliberately requires
        them: a consumer handed a bare grid has lost the only thing stopping a
        wrong count 1 from reading as fact (DESIGN.md §7h). This is the single
        place the field names change from Python to contract spelling; nothing
        downstream should be hand-mapping these.
        """
        if self.count_total is None:
            raise ValueError("count_total is unknown; pass clip_duration_s to propose_grid()")
        return {
            "count_one_s": self.count_one_s,
            "seconds_per_count": self.seconds_per_count,
            "count_total": self.count_total,
            "confidence": self.confidence,
            "bpm": self.bpm,
            "alternates": [
                {"label": a.label, "seconds_per_count": a.seconds_per_count, "bpm": a.bpm}
                for a in self.alternates
            ],
            "warnings": list(self.warnings),
        }


def _extract_audio(source: Path) -> Path:
    """Extract mono 22.05kHz audio from a video via ffmpeg. Returns a temp wav path."""
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "22050", str(tmp)],
        check=True,
    )
    return tmp


def _count_total(count_one_s: float, seconds_per_count: float, clip_duration_s: float) -> int:
    """Mirrors `normalizeStructure`'s countTotal formula in core.ts exactly."""
    return max(1, int((clip_duration_s - count_one_s) // seconds_per_count) + 1)


def propose_grid(source: str | Path, *, clip_duration_s: float | None = None) -> ProposedGrid:
    """Propose a beat grid for a clip. `source` may be a video (audio is
    extracted via ffmpeg) or an audio file directly. `clip_duration_s`, if
    given, fills in `count_total`; without it the field is left None (same
    reasoning as `endS` in core.ts — the caller owns the clip's true end)."""
    source = Path(source)
    audio_path = source if source.suffix.lower() in _AUDIO_EXTS else _extract_audio(source)
    try:
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    finally:
        if audio_path != source:
            audio_path.unlink(missing_ok=True)

    warnings: list[str] = []
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) < 4:
        warnings.append(f"only {len(beat_times)} beats detected; grid is a low-confidence guess")
        seconds_per_count = 60.0 / bpm if bpm > 0 else 0.5
        count_one_s = float(beat_times[0]) if len(beat_times) else 0.0
        confidence = 0.0
    else:
        intervals = np.diff(beat_times)
        seconds_per_count = float(np.median(intervals))
        count_one_s = float(beat_times[0])
        # Regularity: tight, evenly-spaced intervals -> high confidence.
        # Coefficient of variation of 0 -> confidence 1; >=0.5 -> confidence 0.
        cv = float(np.std(intervals) / np.mean(intervals)) if np.mean(intervals) > 0 else 1.0
        regularity = max(0.0, 1.0 - cv / 0.5)
        # Penalize very short beat counts (little evidence).
        coverage = min(1.0, len(beat_times) / 8)
        confidence = round(regularity * coverage, 3)

    alternates = [
        TempoAlternate("double-time", seconds_per_count / 2, bpm * 2),
        TempoAlternate("half-time", seconds_per_count * 2, bpm / 2),
    ]

    if not (_PLAUSIBLE_BPM[0] <= bpm <= _PLAUSIBLE_BPM[1]):
        warnings.append(
            f"tempo {bpm:.0f} BPM is outside the typical {_PLAUSIBLE_BPM[0]}-{_PLAUSIBLE_BPM[1]} dance-practice "
            "range; half/double-time confusion is the likely explanation (see alternates)"
        )
        confidence = min(confidence, 0.4)

    count_total = _count_total(count_one_s, seconds_per_count, clip_duration_s) if clip_duration_s else None

    return ProposedGrid(
        count_one_s=count_one_s,
        seconds_per_count=seconds_per_count,
        count_total=count_total,
        confidence=confidence,
        bpm=bpm,
        alternates=alternates,
        warnings=warnings,
    )
