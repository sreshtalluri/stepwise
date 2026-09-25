"""Audio side of the round-2 research: the Beat This! grid (the production code path) plus
16th-note-resolution accents, for each cached lesson video. Writes .cache/<job>.audio.json.

Runs in the beat-detect package's own env (it has Beat This!, torch-cpu and librosa):

    uv run --project ../../../packages/beat-detect/python python audio.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import librosa
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../../packages/beat-detect/python"))
from beat_detect import propose  # noqa: E402  (the production proposal, unchanged)

SR, HOP = 22050, 128  # 5.8 ms frames: well below a 16th note at any dance tempo


def analyse(video: str) -> dict:
    wav = tempfile.mkstemp(suffix=".wav")[1]
    subprocess.run([propose.imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-i", video, "-vn", "-ac", "1",
                    "-ar", str(SR), wav], check=True)
    try:
        grid = propose.propose_grid(wav)
        y, _ = librosa.load(wav, sr=SR, mono=True)
    finally:
        os.unlink(wav)
    beats, downbeats = propose._track_beats(y, SR)
    # percussive part only: hits, claps, snares and hats, not held notes
    _, perc = librosa.effects.hpss(y)
    env = librosa.onset.onset_strength(y=perc, sr=SR, hop_length=HOP)
    env = env / (np.percentile(env, 99) + 1e-9)
    t_env = librosa.frames_to_time(np.arange(len(env)), sr=SR, hop_length=HOP)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, backtrack=False, units="frames")
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    return {
        "grid": {"count_one_s": grid.count_one_s, "seconds_per_count": grid.seconds_per_count, "bpm": grid.bpm,
                 "confidence": grid.confidence, "warnings": grid.warnings},
        "beats": [round(float(b), 4) for b in beats], "downbeats": [round(float(b), 4) for b in downbeats],
        "onsets": [[round(float(t_env[i]), 4), round(float(env[i]), 3)] for i in on],
        "env_hop_s": HOP / SR, "env": [round(float(v), 3) for v in env],
        "rms_hop_s": 512 / SR, "rms": [round(float(v), 4) for v in rms],
    }


def main():
    cache = os.path.join(HERE, ".cache")
    for f in sorted(os.listdir(cache)):
        if f.endswith(".mp4"):
            out = os.path.join(cache, f[:-4] + ".audio.json")
            r = analyse(os.path.join(cache, f))
            json.dump(r, open(out, "w"))
            g = r["grid"]
            print(f[:12], f"count1 {g['count_one_s']:.3f}  {g['bpm']:.1f} BPM  conf {g['confidence']}  "
                  f"beats {len(r['beats'])}  onsets {len(r['onsets'])}")


if __name__ == "__main__":
    main()
