"""Automatic beat/downbeat *proposal* for a clip's audio.

This is a proposal generator, not a decider (docs/OPEN-DECISIONS.md A5,
docs/DESIGN.md honesty rules). It never claims to know count 1 or the tempo —
it guesses, scores its own confidence, and flags the classic half/double-time
ambiguity so a UI (built later, not here) can let a human overrule it.
`packages/navigation/src/core.ts`'s `gridFromTaps()` is the manual path this
feeds a *starting point* for; manual tap-in always wins.

Beats: Beat This! (`beat-this`, MIT code and weights), CPU. Count 1: a kick
(low-band accent) rule over those beats, via librosa (ISC). See README.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
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

    Any beat tracker (Beat This! included) can lock onto 2x or 0.5x the tempo
    a human would tap. `secondsPerCount` is the SAME anchor grid
    re-hypothesized at a different subdivision — not a different countOneS.
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
    confidence: float  # 0..1, trust in the GRID (tempo + beat spacing), not in which beat is 1
    bpm: float
    alternates: list[TempoAlternate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    count_one_alternates: list[CountOneAlternate] = field(default_factory=list)
    # 0..1, trust in WHICH beat is count 1 (the bar phase). < 0.5: a guess. See _count_one.
    count_one_confidence: float = 0.0

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


@lru_cache(maxsize=1)
def _beat_this():
    """Beat This! (CPJKU, ISMIR 2024; MIT code and weights), `final0`, CPU,
    no DBN. Loaded once per process (~1 s). The checkpoint is baked into the
    Modal image at build time; anywhere else, torch.hub fetches it once into
    ~/.cache/torch/hub/checkpoints."""
    from beat_this.inference import Audio2Beats  # torch: imported only when used

    return Audio2Beats("final0", device="cpu", dbn=False)


def _track_beats(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """(beat times, downbeat times) in seconds. Tests replace this with
    recorded model output so they stay fast and offline."""
    beats, downbeats = _beat_this()(y, sr)
    return np.asarray(beats, float), np.asarray(downbeats, float)


def _fit_grid(beats: np.ndarray) -> tuple[float, float, np.ndarray]:
    """(seconds_per_count, phase_s, idx): the least-squares constant grid
    `phase_s + seconds_per_count * idx` through the model's beats.

    `idx` is each beat's count number, stepped by the rounded gap so a beat
    the model skipped (or doubled) does not shift every later count.
    ponytail: one constant tempo (the contract's grid). A drifting track
    (solo-07, 125 -> 129 BPM) ends up to ~90 ms off at its ends; pass per-beat
    times through the contract if that ever shows.
    """
    gaps = np.diff(beats)
    steps = np.maximum(1, np.round(gaps / np.median(gaps))).astype(int)
    idx = np.concatenate([[0], np.cumsum(steps)])
    spc, phase = np.polyfit(idx, beats, 1)
    return float(spc), float(phase), idx


def _beat_accents(y: np.ndarray, sr: int, beats: np.ndarray) -> np.ndarray:
    """Low-band (<150 Hz, kick) onset strength at each beat, +-50 ms. Tests
    replace this with values recorded from the real clips, like `_track_beats`."""
    hop = 256
    S = np.abs(librosa.stft(y, hop_length=hop))
    low = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(S[librosa.fft_frequencies(sr=sr) < 150]), sr=sr, hop_length=hop)
    ft = librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=hop)
    return np.array([low[(ft > b - 0.05) & (ft < b + 0.05)].max(initial=0.0) for b in beats])


def _count_one(y: np.ndarray, sr: int, beats: np.ndarray, idx: np.ndarray, downbeats: np.ndarray,
               spc: float, phase_s: float) -> tuple[float, float, float, list[CountOneAlternate]]:
    """(count_one_s, margin, phase_confidence, alternates), on the grid `phase_s + spc * n`.

    1. Kick rule: the beat-of-the-bar (idx mod 4) with the strongest low-band
       (<150 Hz) onsets at the model's beats is the bar downbeat. With Beat
       This!'s beats it matched the owner's count 1 on all four labelled clips
       (solo-01, solo-02, group-synced-01, solo-07); Beat This!'s own
       downbeats missed solo-07 by half a bar (docs/research/downbeat-models.md).
    2. When no beat of the bar is >=10% ahead of the runner-up (`margin` <
       1.1) the kick rule is a coin toss, so the model's majority downbeat
       phase decides instead.
    3. Count 1 is the first bar downbeat at or after the first beat the
       model heard (skips a silent intro, keeps a pickup out).

    `alternates` are the other three beats of that bar. When the kick rule
    and the model disagree, the pick that lost goes first (the second guess
    is usually the other one); the rest follow by accent share.

    `phase_confidence` (0..1) is how sure we are WHICH beat is 1 -- separate
    from the grid confidence, which only says the beats are evenly spaced. Two
    independent votes: the kick rule's strength (0 at a tie, 1 when the best
    beat of the bar is >=30% ahead of the runner-up) and the share of the
    model's downbeats on the pick. Both back the pick: 0.5 + 0.5 * the weaker
    vote. Otherwise one source stands alone or they contradict each other:
    at most 0.4, scaled by how lopsided they are. So < 0.5 means "count 1 is
    a guess". On the 10 owner-labelled clips all three misses (one beat off,
    ~150 BPM, kick and model disagreed) scored <= 0.16; see
    evaluation/labels/count_one.json and tests/test_count_one_labels.py.
    """
    if len(beats) < 8:
        return float(beats[0]) if len(beats) else phase_s, 0.0, 0.0, []
    accent = _beat_accents(y, sr, beats)
    scores = np.array([accent[idx % 4 == k].mean() for k in range(4)])
    kick = int(np.argmax(scores))
    runner_up = np.sort(scores)[-2]
    margin = float(scores[kick] / runner_up) if runner_up > 0 else 1.0
    near = [int(idx[np.argmin(np.abs(beats - d))]) % 4 for d in downbeats]
    votes = np.bincount(np.asarray(near, int), minlength=4)
    model = int(votes.argmax()) if near else kick
    k = kick if margin >= 1.1 else model
    strength = min(1.0, max(0.0, (margin - 1.0) / 0.3))
    backing = votes / votes.sum() if near else np.zeros(4)
    if near and k == kick == model:
        phase_confidence = 0.5 + 0.5 * min(strength, float(backing[k]))
    else:
        phase_confidence = 0.4 * abs(strength - float(backing[model]))
    other = model if k == kick else kick
    # idx starts at 0 on the first beat heard, so count 1 is grid count k.
    share = scores / scores.sum() if scores.sum() > 0 else np.full(4, 0.25)
    rest = sorted((i for i in range(4) if i != k), key=lambda i: (i != other, -share[i]))
    alternates = [CountOneAlternate(float(phase_s + spc * i), i - k, round(float(share[i]), 3)) for i in rest]
    return float(phase_s + spc * k), margin, round(phase_confidence, 3), alternates


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
    beat_times, downbeat_times = _track_beats(y, sr)

    if len(beat_times) < 4:
        warnings.append(f"only {len(beat_times)} beats detected; grid is a low-confidence guess")
        seconds_per_count = float(np.median(np.diff(beat_times))) if len(beat_times) > 1 else 0.5
        count_one_s = float(beat_times[0]) if len(beat_times) else 0.0
        confidence = 0.0
        count_one_confidence = 0.0
    else:
        seconds_per_count, phase_s, idx = _fit_grid(beat_times)
        count_one_s, downbeat_margin, count_one_confidence, count_one_alternates = _count_one(
            y, sr, beat_times, idx, downbeat_times, seconds_per_count, phase_s)
        if downbeat_margin < 1.1:
            warnings.append("no beat of the bar is clearly accented; count 1 is a weak guess")
        # Regularity: tight, evenly-spaced intervals -> high confidence.
        # Coefficient of variation of 0 -> confidence 1; >=0.5 -> confidence 0.
        intervals = np.diff(beat_times) / np.diff(idx)
        cv = float(np.std(intervals) / np.mean(intervals)) if np.mean(intervals) > 0 else 1.0
        regularity = max(0.0, 1.0 - cv / 0.5)
        # Penalize very short beat counts (little evidence).
        coverage = min(1.0, len(beat_times) / 8)
        confidence = round(regularity * coverage, 3)
    bpm = 60.0 / seconds_per_count

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
        count_one_confidence=count_one_confidence,
    )
