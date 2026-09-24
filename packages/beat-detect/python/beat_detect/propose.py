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

import imageio_ffmpeg
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
class CountOneAlternate:
    """Another beat that could be count 1, on the same grid.

    `shift_counts` is how far it sits from the proposal's count 1 (-1 = one
    count earlier). `confidence` is the share of the music's low-band accent
    that falls on this beat-of-the-bar -- how hard the track leans on it, NOT a
    probability that the dancer counts from it (solo-02's truth has the weaker
    accent). Ordered strongest first, so a UI's "try another 1" can walk them.
    """

    count_one_s: float
    shift_counts: int
    confidence: float


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
    count_one_alternates: list[CountOneAlternate] = field(default_factory=list)

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


def _extract_audio(source: Path) -> Path:
    """Extract mono 22.05kHz audio from a video via ffmpeg. Returns a temp wav path.

    The ffmpeg is imageio-ffmpeg's pinned static build (7.x), never the system
    one. TikTok audio is HE-AAC with an edit list trimming the encoder
    priming; Debian bookworm's ffmpeg 5.1 (what `apt install ffmpeg` gave the
    Modal beat image) trims it twice, so the whole track -- and count 1 --
    came out 115 ms early on solo-02 (1.789 s on Modal vs 1.905 s locally).
    """
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "22050", str(tmp)],
        check=True,
    )
    return tmp


def _refine_grid(y: np.ndarray, sr: int, spc0: float) -> tuple[float, float]:
    """(seconds_per_count, phase_s) of the constant grid that best fits the onsets.

    librosa's tempo is quantized to whole 512-sample frames of lag: at 22.05 kHz
    the only readings near 115-120 BPM are 112.3 / 117.5 / 123.0 / 129.2, and
    `beat_track` spaces its beats at that period. A 2% tempo error drifts the
    grid half a beat off within ~25 counts (solo-02: 117.45 read vs 115.07 true,
    count 25 lands 0.25 s off the beat). So: keep librosa's reading only as the
    starting point and search +-6% around it -- more than one quantization step,
    well short of half/double -- at 0.5 ms / 4 ms resolution for the spacing and
    phase whose grid lands on the most onset energy.
    """
    hop = 128  # ~6 ms envelope; 512 is what caused the quantization
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    ft = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=hop)
    best = (-1.0, spc0, 0.0)
    for spc in np.arange(spc0 * 0.94, spc0 * 1.06, 0.0005):
        n = int((ft[-1] - spc) / spc)
        if n < 2:
            break
        phases = np.arange(0.0, spc, 0.004)
        score = np.interp(phases[:, None] + spc * np.arange(n), ft, env).mean(axis=1)
        i = int(np.argmax(score))
        if score[i] > best[0]:
            best = (float(score[i]), float(spc), float(phases[i]))
    return best[1], best[2]


def _count_one(y: np.ndarray, sr: int, spc: float, phase_s: float, music_start_s: float
               ) -> tuple[float, float, list[CountOneAlternate]]:
    """(count_one_s, margin, alternates).

    1. The beat-of-the-bar (mod 4) with the strongest low-band (<150 Hz, kick)
       onsets is the bar downbeat. Beat This! and madmom agree with it on all
       four eval clips' bar phase.
    2. But the dancer's 1 is not the bar's 1: on solo-02 (the one clip with an
       owner label) the eight starts HALF A BAR before the downbeat all three
       music models find (0.862 s vs 1.905 s). So count 1 is the EARLIEST
       strong beat -- the downbeat or the half-bar beat, same parity -- at or
       after the music starts: a clip is trimmed to where the dance starts, and
       the music's strong beats are the only ones a dancer counts 1 on.

    ponytail: fit to ONE labelled clip. The two rules disagree on solo-01 and
    solo-07; the owner's set-count-1 taps on more clips decide it (README).
    `margin` is the downbeat phase's score over the runner-up. `alternates` are
    the other three beats of the bar, strongest accent first.
    """
    hop = 256
    S = np.abs(librosa.stft(y, hop_length=hop))
    low = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(S[librosa.fft_frequencies(sr=sr) < 150]), sr=sr, hop_length=hop)
    ft = librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=hop)
    beats = phase_s + spc * np.arange(int((ft[-1] - 0.05 - phase_s) / spc) + 1)
    if len(beats) < 8:
        return float(beats[0]) if len(beats) else phase_s, 0.0, []
    accent = np.array([low[(ft > b - 0.05) & (ft < b + 0.05)].max() for b in beats])
    scores = np.array([accent[k::4].mean() for k in range(4)])
    k = int(np.argmax(scores))
    runner_up = np.sort(scores)[-2]
    margin = float(scores[k] / runner_up) if runner_up > 0 else 1.0
    # Skip beats before librosa heard any music (silent intro), half a beat of slack.
    first = int(np.searchsorted(beats, music_start_s - spc / 2))
    first = min(first, len(beats) - 4)
    one = first + (k - first) % 2  # earliest beat with the downbeat's parity
    share = scores / scores.sum() if scores.sum() > 0 else np.full(4, 0.25)
    alternates = [
        CountOneAlternate(float(beats[i]), int(i - one), round(float(share[i % 4]), 3))
        for i in sorted(range(first, first + 4), key=lambda i: -share[i % 4]) if i != one
    ]
    return float(beats[one]), margin, alternates


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
    count_one_alternates: list[CountOneAlternate] = []
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
        seconds_per_count, phase_s = _refine_grid(y, sr, float(np.median(intervals)))
        bpm = 60.0 / seconds_per_count
        count_one_s, downbeat_margin, count_one_alternates = _count_one(y, sr, seconds_per_count, phase_s, float(beat_times[0]))
        if downbeat_margin < 1.1:
            warnings.append("no beat of the bar is clearly accented; count 1 is a weak guess")
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
        count_one_alternates=count_one_alternates,
    )
