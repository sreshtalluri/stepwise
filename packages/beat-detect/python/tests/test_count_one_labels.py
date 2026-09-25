"""Count 1 against the owner's labels (evaluation/labels/count_one.json).

A hit is the same bar phase as the label and within 70 ms of it (label moved
by whole bars). Offline, this replays Beat This!'s recorded beats, downbeats
and per-beat kick accents for each clip (tests/fixtures/beat-this-recorded.json),
so it runs the real grid fit and count-1 rule without the model or the video.

Scoring the live model on real audio instead:

    uv run python tests/test_count_one_labels.py DIR   # DIR/<clip>.mp4 per label
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from beat_detect import propose
from beat_detect.propose import propose_grid

ROOT = Path(__file__).resolve().parents[4]
LABELS = json.loads((ROOT / "evaluation/labels/count_one.json").read_text())["labels"]
RECORDED = json.loads((Path(__file__).parent / "fixtures/beat-this-recorded.json").read_text())
PHASE_CONFIDENT = 0.5  # count_one_confidence below this: count 1 is a guess

# Known misses, 2026-09-25: all ~150 BPM, all exactly one beat off, all with
# the kick rule overruling the model's (correct) downbeat. A fix flips these
# to XPASS, which fails the run (strict) until the entry is removed here.
KNOWN_MISSES = {"mirror", "mirror-cut-12s", "tiktok-44s"}
# Hits where the kick rule and the model disagree or the kick rule is a tie,
# so phase confidence is honestly low even though the pick was right.
LOW_CONFIDENCE_HITS = {"solo-07", "hoodie-followcam"}


def score(label: dict, count_one_s: float, spc: float) -> tuple[bool, int, float]:
    """(hit, bar phase off in beats -2..1 (-1 = one beat early), ms off after
    moving the label by whole beats)."""
    n = round((count_one_s - label["count_one_s"]) / spc)
    off_ms = (count_one_s - (label["count_one_s"] + n * spc)) * 1000
    phase = (n + 2) % 4 - 2
    return phase == 0 and abs(off_ms) <= 70, phase, off_ms


def _replay(monkeypatch, tmp_path, clip):
    rec = RECORDED[clip]
    monkeypatch.setattr(propose, "_track_beats",
                        lambda y, sr: (np.asarray(rec["beats"], float), np.asarray(rec["downbeats"], float)))
    monkeypatch.setattr(propose, "_beat_accents", lambda y, sr, beats: np.asarray(rec["accents"], float))
    wav = tmp_path / "silence.wav"
    sf.write(str(wav), np.zeros(22050, np.float32), 22050)
    return propose_grid(wav)


@pytest.mark.parametrize("label", [
    pytest.param(lb, id=lb["clip"], marks=pytest.mark.xfail(
        strict=True, reason="known miss: one beat off at ~150 BPM, kick rule overrules the model"))
    if lb["clip"] in KNOWN_MISSES else pytest.param(lb, id=lb["clip"])
    for lb in LABELS])
def test_count_one_matches_the_owner_label(label, monkeypatch, tmp_path):
    result = _replay(monkeypatch, tmp_path, label["clip"])
    hit, phase, off_ms = score(label, result.count_one_s, result.seconds_per_count)
    assert hit, f"phase {phase:+d} beat, {off_ms:+.0f} ms"


def test_phase_confidence_is_low_exactly_where_count_one_is_a_guess(monkeypatch, tmp_path):
    """Grid confidence stays ~0.95 on the misses; count_one_confidence must not."""
    got = {}
    for label in LABELS:
        result = _replay(monkeypatch, tmp_path, label["clip"])
        hit, _, _ = score(label, result.count_one_s, result.seconds_per_count)
        assert hit == (label["clip"] not in KNOWN_MISSES), label["clip"]
        assert result.confidence > 0.9, label["clip"]  # the grid is right everywhere
        got[label["clip"]] = result.count_one_confidence
    low = {c for c, v in got.items() if v < PHASE_CONFIDENT}
    assert low == KNOWN_MISSES | LOW_CONFIDENCE_HITS, got


def main(clip_dir: Path) -> None:
    hits = 0
    for label in LABELS:
        mp4 = clip_dir / f"{label['clip']}.mp4"
        if not mp4.exists():
            print(f"{label['clip']:18s} (no {mp4.name})")
            continue
        r = propose_grid(mp4)
        hit, phase, off_ms = score(label, r.count_one_s, r.seconds_per_count)
        hits += hit
        print(f"{label['clip']:18s} {'HIT ' if hit else 'MISS'} label {label['count_one_s']:.3f} got {r.count_one_s:.3f} "
              f"(phase {phase:+d} beat, {off_ms:+.0f} ms)  bpm {r.bpm:.1f}  grid conf {r.confidence:.2f}  "
              f"count-1 conf {r.count_one_confidence:.2f}")
    print(f"{hits}/{len(LABELS)} hits")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
