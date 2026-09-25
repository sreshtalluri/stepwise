"""A/V sync from hand contacts: when the two wrists meet (3D, sub-sample by a parabola through
the distance minimum) there is usually a clap or a hit on the audio. Median lag to the nearest
percussive onset = the file's A/V offset plus the dancer's own timing.

    python claps.py
"""
from __future__ import annotations

import json
import os

import numpy as np

from segment import HERE, LESSONS, kinematics

C = os.path.join(HERE, ".cache")
CONTACT_M = 0.15   # wrists this close = hands together
WINDOW_S = 0.15    # nearest onset within this


def main():
    for job, name in LESSONS.items():
        doc = json.load(open(os.path.join(C, f"{job}.json")))
        au = json.load(open(os.path.join(C, f"{job}.audio.json")))
        k = kinematics(doc)
        ix, t = k["ix"], k["t"]
        d = np.linalg.norm(k["body"][:, ix["l_wrist"]] - k["body"][:, ix["r_wrist"]], axis=1)
        seen = k["vis"][:, [ix["l_wrist"], ix["r_wrist"]]].min(1) == 2
        # approach speed before the contact: a clap closes fast, resting hands do not
        contacts = []
        for i in range(2, len(d) - 2):
            if seen[i] and d[i] < CONTACT_M and d[i] <= d[i - 2:i + 3].min() and d[i - 2] - d[i] > 0.12:
                a, b, c = d[i - 1], d[i], d[i + 1]
                den = a - 2 * b + c
                off = 0.5 * (a - c) / den if den > 1e-9 else 0.0
                contacts.append(t[i] + np.clip(off, -0.5, 0.5) * (t[i + 1] - t[i]))
        ons = np.array([o[0] for o in au["onsets"] if o[1] > 0.2])
        lags = []
        for c in contacts:
            j = np.argmin(np.abs(ons - c))
            if abs(ons[j] - c) <= WINDOW_S:
                lags.append(c - ons[j])  # + = hands meet after the sound
        lags = np.array(lags)
        if len(lags):
            print(f"{name:8s} contacts {len(contacts):3d}  matched {len(lags):3d}  median {1000 * np.median(lags):+5.0f} ms  "
                  f"IQR {1000 * np.percentile(lags, 25):+.0f}..{1000 * np.percentile(lags, 75):+.0f} ms")
        else:
            print(f"{name:8s} contacts {len(contacts):3d}  matched 0")


if __name__ == "__main__":
    main()
