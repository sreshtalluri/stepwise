"""2D motion at the video's native frame rate, no model: frame-difference energy inside the
dancer's box (union of the MotionResult's hand/foot crop rects, padded). Writes
.cache/<job>.video2d.json. This is the cheapest stand-in for "2D keypoints at native fps":
it sees hits (sudden stops) at 30/60 fps, but cannot say which limb.

    python video2d.py        # needs ffmpeg on PATH and numpy
"""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W = 160  # analysis width in px; height follows the aspect


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,avg_frame_rate:stream_side_data=rotation", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["avg_frame_rate"].split("/")
    return s["width"], s["height"], float(num) / float(den)


def frames(path, w, h):
    """Gray frames, scaled to width W, with their presentation times (ffmpeg applies rotation)."""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={W}:-2,format=gray", "-f", "rawvideo",
                           "-"], capture_output=True, check=True)
    pts = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.split()
    t = np.array([float(x.strip(",")) for x in pts if x.strip(",") not in ("", "N/A")])
    buf = np.frombuffer(proc.stdout, np.uint8)
    hh = len(buf) // (W * len(t)) if len(t) else 0
    n = len(buf) // (W * hh)
    return buf[: n * W * hh].reshape(n, hh, W).astype(np.float32), t[:n]


def dancer_box(doc):
    """Per-sample [x0,y0,x1,y1] (normalised) from the hand/foot crop rects, padded; None when unknown."""
    cr = doc["persons"][0]["crop_rects"]
    boxes = []
    for i in range(len(doc["sample_times_s"])):
        rs = [cr[k][i] for k in ("left_hand", "right_hand", "left_foot", "right_foot", "hands", "feet") if cr[k][i]]
        if not rs:
            boxes.append(None)
            continue
        x0 = min(r["x"] for r in rs); y0 = min(r["y"] for r in rs)
        x1 = max(r["x"] + r["width"] for r in rs); y1 = max(r["y"] + r["height"] for r in rs)
        px, py = 0.15 * (x1 - x0), 0.10 * (y1 - y0)
        boxes.append([max(0, x0 - px), max(0, y0 - 2 * py), min(1, x1 + px), min(1, y1 + py)])
    return boxes


def analyse(job):
    cache = os.path.join(HERE, ".cache")
    doc = json.load(open(os.path.join(cache, f"{job}.json")))
    video = os.path.join(cache, f"{job}.mp4")
    _, _, fps = probe(video)
    F, t = frames(video, 0, 0)
    st = np.array(doc["sample_times_s"])
    boxes = dancer_box(doc)
    n, H, _ = F.shape
    energy = np.zeros(n)
    for i in range(1, n):
        j = int(np.clip(np.searchsorted(st, t[i]), 0, len(st) - 1))
        b = boxes[j] or [0, 0, 1, 1]
        y0, y1 = int(b[1] * H), max(int(b[1] * H) + 2, int(b[3] * H))
        x0, x1 = int(b[0] * W), max(int(b[0] * W) + 2, int(b[2] * W))
        d = np.abs(F[i, y0:y1, x0:x1] - F[i - 1, y0:y1, x0:x1])
        energy[i] = float(np.mean(d > 12))  # share of box pixels that changed: robust to lighting noise
    energy[0] = energy[1]
    return {"fps": fps, "t": [round(float(x), 4) for x in t], "energy": [round(float(x), 4) for x in energy]}


def main():
    cache = os.path.join(HERE, ".cache")
    for f in sorted(os.listdir(cache)):
        if f.endswith(".mp4"):
            job = f[:-4]
            r = analyse(job)
            json.dump(r, open(os.path.join(cache, f"{job}.video2d.json"), "w"))
            print(job[:12], f"{r['fps']:.2f} fps, {len(r['t'])} frames")


if __name__ == "__main__":
    main()
