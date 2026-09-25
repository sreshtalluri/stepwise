"""Round-2 measurements: timeline alignment and fast (sub-beat) passages.

Needs .cache/<job>.json, .audio.json (audio.py) and .video2d.json (video2d.py).

    python sync.py      # prints the tables quoted in docs/research/step-by-step-learning.md §8–9

1. 3D vs video: lag between the 3D energy (15 fps) and native-fps frame-difference energy.
   0 means sample_times_s is on the video's clock.
2. Motion vs audio: lag between visible hits (2D deceleration peaks) and percussive onsets.
   Mixed together here are the dancer's own timing and any A/V offset in the file.
3. Motion vs grid: where visible hits fall inside a count (0 = on the count, 0.5 = on the "and").
4. Fast passages: windows of one count with >=3 visible hits AND >=3 audio onsets.
"""
from __future__ import annotations

import json
import os

import numpy as np

from segment import HERE, LESSONS, fast_counts, kinematics

C = os.path.join(HERE, ".cache")


def load(job):
    doc = json.load(open(os.path.join(C, f"{job}.json")))
    au = json.load(open(os.path.join(C, f"{job}.audio.json")))
    v2 = json.load(open(os.path.join(C, f"{job}.video2d.json")))
    return doc, au, v2


def xcorr_lag(a_t, a, b_t, b, max_lag=0.3, step=0.005):
    """Lag (s) that best aligns b to a: positive = b happens later than a."""
    lags = np.arange(-max_lag, max_lag + 1e-9, step)
    grid = np.arange(max(a_t[0], b_t[0]) + max_lag, min(a_t[-1], b_t[-1]) - max_lag, step)
    A = np.interp(grid, a_t, a)
    A = (A - A.mean()) / (A.std() + 1e-9)
    best, lag = -9.0, 0.0
    scores = []
    for L in lags:
        B = np.interp(grid + L, b_t, b)
        B = (B - B.mean()) / (B.std() + 1e-9)
        s = float(np.mean(A * B))
        scores.append(s)
        if s > best:
            best, lag = s, float(L)
    return lag, best, float(np.median(scores))


def hits_2d(v2):
    """Visible hits: peaks of deceleration of the native-fps 2D energy (motion that suddenly stops)."""
    # frame i's difference is between frames i-1 and i: it belongs half a frame earlier
    t, e = np.array(v2["t"]) - 0.5 / v2["fps"], np.array(v2["energy"])
    k = 1
    es = np.convolve(e, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    dec = np.maximum(0, -np.gradient(es, t))
    thr = np.percentile(dec, 75)
    peaks = [i for i in range(2, len(dec) - 2) if dec[i] >= dec[i - 2:i + 3].max() and dec[i] > thr]
    # a hit is the moment of hardest braking. (Round 2 first used the energy minimum AFTER the braking,
    # and that sat a steady ~1/8 count late on every clip: the body is already still by then.)
    return t, es, dec, [(t[i], dec[i]) for i in peaks]


def main():
    rows = []
    for job, name in LESSONS.items():
        doc, au, v2 = load(job)
        k = kinematics(doc)
        g = au["grid"]
        one, spc = g["count_one_s"], g["seconds_per_count"]
        pc = doc["proposed_counts"]
        t2, e2, dec, hits = hits_2d(v2)
        env_t = np.arange(len(au["env"])) * au["env_hop_s"]
        env = np.array(au["env"])

        lag3d, s3d, _ = xcorr_lag(t2, e2, k["t"], k["energy"])
        lag_av, s_av, s_med = xcorr_lag(env_t, env, t2, dec)
        dancing = (np.array([h[0] for h in hits]) > k["t"][0])
        ht = np.array([h[0] for h in hits])
        phase = ((ht - one) / spc) % 1.0
        hist = np.histogram(phase, bins=8, range=(0, 1))[0]
        # offset of each hit from the nearest half-beat, for hits within 1/8 count of one (ms). Its median is
        # A/V offset + pipeline offset + the dancer's own timing, together; they cannot be separated here.
        dev = ((ht - one) / (spc / 2) + 0.5) % 1.0 - 0.5
        near = dev[np.abs(dev) <= 0.25] * spc / 2 * 1000
        hist = (hist, float(np.median(near)) if len(near) else float("nan"), len(near))
        # onsets per count and hits per count, per count window
        ons = np.array([o[0] for o in au["onsets"] if o[1] > 0.25])
        n_counts = int((k["t"][-1] - one) / spc)
        fast = [round(one + c * spc, 2) for c in fast_counts(ht, ons, one, spc)]
        # chance: the same test with the hits shifted by a random non-grid offset (keeps their density)
        rng = np.random.default_rng(0)
        null = [len(fast_counts(ht + rng.uniform(0.1, 0.9) * spc, ons, one, spc)) for _ in range(200)]
        fast = (fast, float(np.mean(null)), float(np.percentile(null, 95)))
        # groove phase: where in the beat the pelvis is lowest (bounce) and the 2D motion is stillest,
        # from the Fourier component at the beat frequency over the whole dance (sub-sample precise)
        def trough_ms(tt, x):
            m = (tt > k["t"][0]) & (tt < k["t"][-1])
            z = np.sum((x[m] - x[m].mean()) * np.exp(-2j * np.pi * (tt[m] - one) / spc))
            peak = (-np.angle(z) / (2 * np.pi)) % 1.0          # phase of the maximum
            strength = abs(z) / (np.sqrt(np.sum((x[m] - x[m].mean()) ** 2) * m.sum()) + 1e-9)
            return int(round(1000 * (((peak + 0.5) % 1.0 + 0.5) % 1.0 - 0.5) * spc)), round(float(strength), 2)
        height = (k["root"] - k["root"][0]) @ k["up"]
        groove = (trough_ms(k["t"], height), trough_ms(t2, e2))
        rows.append((name, pc["count_one_s"], one, spc, lag3d, s3d, lag_av, s_av, s_med, hist, len(ht), fast, n_counts,
                     groove))

    print("| lesson | live count 1 | Beat This! count 1 | 3D-vs-video lag | hits-vs-onsets lag (corr / median) |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]:.3f} | {r[2]:.3f} | {1000 * r[4]:+.0f} ms (r={r[5]:.2f}) | {1000 * r[6]:+.0f} ms ({r[7]:.2f} / {r[8]:.2f}) |")
    print("\nwhere visible hits land inside a count (8 bins; bin 0 = on the count, bin 4 = on the 'and'):")
    for r in rows:
        h, off, n_near = r[9]
        print(f"  {r[0]:8s} n={r[10]:3d}  " + " ".join(f"{x:3d}" for x in h) +
              f"   on-count(bins 7,0,1)={h[7] + h[0] + h[1]}  on-and(bins 3,4,5)={h[3] + h[4] + h[5]}"
              f"   median offset from nearest half-beat {off:+.0f} ms (n={n_near})")
    print("\ngroove phase (ms from the nearest count; strength 0..1 of the beat-frequency component):")
    for r in rows:
        (hp, hs), (ep, es) = r[13]
        print(f"  {r[0]:8s} pelvis lowest {hp:+4d} ms (strength {hs})   2D stillest {ep:+4d} ms (strength {es})")
    print("\nfast counts (>=3 of 4 sixteenth positions with a visible hit AND >=3 with an onset; chance = hits shifted off-grid):")
    for r in rows:
        f, mu, p95 = r[11]
        print(f"  {r[0]:8s} {len(f)}/{r[12]} counts (chance mean {mu:.1f}, 95th pct {p95:.0f}): {f[:12]}")


if __name__ == "__main__":
    main()
