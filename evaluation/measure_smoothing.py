"""W9 verification: what temporal smoothing did to a real clip, in numbers.

Not a test (that is tools/test_smoothing.py, which needs no data) -- this is
the "measure, do not trust" harness that produced the numbers in
docs/GATE-REPORT.md's W9 addendum. Re-run it on any run_clip() npz:

    modal volume get stepwise-results solo-01.npz /tmp/solo-01.npz
    python evaluation/measure_smoothing.py /tmp/solo-01.npz

It reports three things, because two of them are easy to fake:

  1. Jitter before/after -- the defect W9 exists to fix.
  2. How many joint-samples got marked uncertain/absent, and why.
  3. Whether the dance survived. Jitter can always be driven to zero by
     deleting the motion, so a jitter number alone proves nothing. The
     accent check compares peak speed at the clip's sharpest real motion
     events against the same events under a moving average tuned to remove
     the *same* amount of jitter -- if the Kalman chain is just a blur, it
     will smear the accents as badly as the blur does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services/motion-api/vendor/fast-sam-3d-body/tools"))

import smoothing as sm  # noqa: E402

FPS = 15.0


def load(npz_path: str, track_id: int | None = None):
    """Rebuild exactly the dict `process_clip()` hands to the smoother, so the
    numbers below come from the shipped code path, not a copy of it."""
    data = np.load(npz_path, allow_pickle=True)
    if bool(data["refused"]):
        raise SystemExit(f"{npz_path} was refused by run_clip, nothing to measure")
    hierarchy = json.loads((REPO / "services/motion-api/mhr_joint_hierarchy.json").read_text())
    parents = np.array([j["parent_index"] for j in hierarchy["joints"]])
    names = [j["name"] for j in hierarchy["joints"]]
    tid = track_id if track_id is not None else int(data["confident_track_ids"][0])
    result = {
        "per_frame": data["per_frame"],
        "raw_detections": data["raw_detections"],
        "sample_times_s": data["sample_times_s"],
        "confident_track_ids": [tid],
        # Older npz files predate the frame_width/height keys (added in W4).
        # solo-01/solo-07 are 576x1024 per docs/GATE-REPORT.md.
        "frame_width": int(data["frame_width"]) if "frame_width" in data.files else 576,
        "frame_height": int(data["frame_height"]) if "frame_height" in data.files else 1024,
    }
    F, J = len(result["per_frame"]), len(parents)
    raw = np.zeros((F, J, 8))
    observed = np.zeros(F, dtype=bool)
    for i in range(F):
        person = result["per_frame"][i].get(tid) if isinstance(result["per_frame"][i], dict) else None
        if person is not None and "skel_state" in person:
            raw[i] = person["skel_state"]
            observed[i] = True
    return result, hierarchy, names, parents, tid, raw, observed


def jitter(positions_m: np.ndarray) -> dict:
    step = np.linalg.norm(np.diff(positions_m, axis=0), axis=-1)
    per_frame_mean = step.mean(axis=1)
    per_frame_max = step.max(axis=1)
    return {
        "mean_m": float(per_frame_mean.mean()),
        "mean_p90_m": float(np.percentile(per_frame_mean, 90)),
        "mean_p99_m": float(np.percentile(per_frame_mean, 99)),
        "maxjoint_mean_m": float(per_frame_max.mean()),
        "maxjoint_p90_m": float(np.percentile(per_frame_max, 90)),
        "maxjoint_p99_m": float(np.percentile(per_frame_max, 99)),
        "maxjoint_max_m": float(per_frame_max.max()),
        "worst_speed_mps": float(per_frame_max.max() * FPS),
    }


def moving_average(positions_m: np.ndarray, window: int) -> np.ndarray:
    """The strawman: a centred box filter, the thing everyone reaches for."""
    pad = window // 2
    padded = np.pad(positions_m, ((pad, pad), (0, 0), (0, 0)), mode="edge")
    kernel = np.ones(window) / window
    out = np.empty_like(positions_m)
    for j in range(positions_m.shape[1]):
        for c in range(3):
            out[:, j, c] = np.convolve(padded[:, j, c], kernel, mode="valid")[: positions_m.shape[0]]
    return out


def accent_report(raw: np.ndarray, smoothed: np.ndarray, label: str, peaks: np.ndarray) -> dict:
    """Peak body speed retained at the clip's sharpest real motion events."""
    speed_raw = np.linalg.norm(np.diff(raw, axis=0), axis=-1).mean(axis=1) * FPS
    speed_new = np.linalg.norm(np.diff(smoothed, axis=0), axis=-1).mean(axis=1) * FPS
    retained = speed_new[peaks] / np.maximum(speed_raw[peaks], 1e-9)
    # Timing: cross-correlate the two motion-energy curves; a smoother that
    # lags shows up as a non-zero best shift.
    a = speed_raw - speed_raw.mean()
    b = speed_new - speed_new.mean()
    corr = np.correlate(b, a, mode="full")
    shift = int(np.argmax(corr) - (len(a) - 1))
    return {
        "smoother": label,
        "accent_peak_speed_retained_mean": float(retained.mean()),
        "accent_peak_speed_retained_min": float(retained.min()),
        "lag_frames": shift,
    }


def band_power(positions_m: np.ndarray) -> dict:
    """Power below 3 Hz is choreography; above 5 Hz no limb goes (15 fps
    Nyquist is 7.5 Hz). A smoother that eats the low band is eating the dance."""
    x = positions_m - positions_m.mean(axis=0, keepdims=True)
    spec = np.abs(np.fft.rfft(x, axis=0)) ** 2
    freqs = np.fft.rfftfreq(x.shape[0], d=1.0 / FPS)
    low = spec[(freqs > 0) & (freqs <= 3.0)].sum()
    high = spec[freqs >= 5.0].sum()
    return {"power_0_3hz": float(low), "power_5hz_plus": float(high)}


def main(npz_path: str) -> None:
    clip, hierarchy, names, parents, tid, raw, observed = load(npz_path)
    result = sm.smooth_clip_result(clip, hierarchy)[tid]

    idx = np.flatnonzero(observed)
    raw_pos = raw[idx][:, :, :3] / 100.0
    new_pos = result["skel_states"][idx][:, :, :3] / 100.0
    visibility = result["visibility"][idx]

    print(f"=== {Path(npz_path).name}  track {tid}  "
          f"{len(idx)}/{len(observed)} frames reconstructed ===\n")
    print("-- jitter (world joint positions, consecutive reconstructed frames)")
    before, after = jitter(raw_pos), jitter(new_pos)
    for key in before:
        print(f"   {key:22s} raw {before[key]:8.4f}   smoothed {after[key]:8.4f}   "
              f"({100 * (after[key] - before[key]) / before[key]:+.1f}%)")
    # The same numbers over the samples the result actually *claims* to have
    # observed. A held-then-caught-up joint is flagged `uncertain`, so counting
    # it as a broken claim would be double-charging the honesty flags.
    claimed = (visibility[:-1] == sm.OBSERVED) & (visibility[1:] == sm.OBSERVED)
    for label, pos in (("raw", raw_pos), ("smoothed", new_pos)):
        step = np.linalg.norm(np.diff(pos, axis=0), axis=-1)
        print(f"   claimed-observed samples only ({claimed.sum()}/{claimed.size}): {label:9s}"
              f" mean {step[claimed].mean():.4f}  max {step[claimed].max():.4f}")

    print("\n-- suppression")
    stats = result["stats"]
    total = stats["n_frames"] * stats["n_joints"]
    for key in ("n_samples_observed", "n_samples_uncertain", "n_samples_absent"):
        print(f"   {key:26s} {stats[key]:7d}  ({100 * stats[key] / total:5.2f}% of {total} joint-samples)")
    print(f"   {'n_samples_implausible':26s} {stats['n_samples_implausible']:7d}   "
          f"(measured motion above {stats['implausible_gate_m']:.3f} m per frame -> marked uncertain)")
    print(f"   {'n_blocks_gated':26s} {stats['n_blocks_gated']:7d}   "
          f"(filter updates refused: innovation above {stats['innovation_gate_m']:.3f} m at the lever arm)")
    print(f"   {'n_updates_skipped_suppressed':26s} {stats['n_updates_skipped_suppressed']:7d}")
    by_reason = {name: int((result['suppression'] == i).sum()) for i, name in enumerate(sm.SUPPRESSION_NAMES)}
    print(f"   by reason: {by_reason}")
    worst = np.argsort(-(result['visibility'] > 0).sum(axis=0))[:8]
    print("   most-suppressed joints: "
          + ", ".join(f"{names[j]}={int((result['visibility'][:, j] > 0).sum())}" for j in worst))

    print("\n-- did the dance survive?")
    # Accents = peaks of the raw body-speed curve that are real motion, not
    # single-frame spikes: found on a lightly median-filtered curve so the
    # noise the smoother is supposed to remove cannot define its own target.
    speed = np.linalg.norm(np.diff(raw_pos, axis=0), axis=-1).mean(axis=1) * FPS
    med = np.array([np.median(speed[max(0, i - 1): i + 2]) for i in range(len(speed))])
    peaks = np.array([i for i in range(1, len(med) - 1)
                      if med[i] > med[i - 1] and med[i] >= med[i + 1] and med[i] > np.percentile(med, 80)])
    print(f"   {len(peaks)} real accents found (local maxima of the median-filtered body-speed curve)")
    kalman = accent_report(raw_pos, new_pos, "kalman+suppression", peaks)
    # Tune the strawman to the SAME jitter reduction, so the comparison is
    # fair: whatever window matches this chain's mean per-frame displacement.
    target = after["mean_m"]
    best = None
    for window in (3, 5, 7, 9, 11):
        ma = moving_average(raw_pos, window)
        err = abs(jitter(ma)["mean_m"] - target)
        if best is None or err < best[0]:
            best = (err, window, ma)
    _, window, ma = best
    strawman = accent_report(raw_pos, ma, f"moving average (w={window})", peaks)
    for report in (kalman, strawman):
        print(f"   {report['smoother']:28s} peak speed retained "
              f"mean {report['accent_peak_speed_retained_mean']:.3f} "
              f"worst {report['accent_peak_speed_retained_min']:.3f}   "
              f"lag {report['lag_frames']} frames")
    print(f"   (moving average matched to the same jitter: "
          f"mean {jitter(ma)['mean_m']:.4f} m vs {target:.4f} m)")

    raw_band, new_band, ma_band = band_power(raw_pos), band_power(new_pos), band_power(ma)
    print(f"   spectrum: 0-3 Hz power kept  kalman {100 * new_band['power_0_3hz'] / raw_band['power_0_3hz']:.1f}%"
          f"   moving-avg {100 * ma_band['power_0_3hz'] / raw_band['power_0_3hz']:.1f}%")
    print(f"             5-7.5 Hz power kept kalman {100 * new_band['power_5hz_plus'] / raw_band['power_5hz_plus']:.1f}%"
          f"   moving-avg {100 * ma_band['power_5hz_plus'] / raw_band['power_5hz_plus']:.1f}%")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/solo-01.npz")
