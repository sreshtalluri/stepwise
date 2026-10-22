"""Run every beat model we can on every lesson video, for the labelling page.

    uv run --project packages/beat-detect/python python tools/beat-labeler/prep.py

Reads data/media/<job_id>.mp4 and data/queue.json (GET /owner/queue, for what
production shipped), writes data/clips.json. data/ is git-ignored: the repo is
public and holds no lesson ids or video.

Candidates per clip:
  shipped  what the live lesson carries (proposed_counts at upload time)
  final0   propose_grid() as on this branch (Beat This! final0 + kick rule + half-time fix)
  small0   the same rules over Beat This! small0 (scored 4/4 on count 1 on 2026-09-24)
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import librosa
import numpy as np

from beat_detect import propose

HERE = Path(__file__).parent
DATA = HERE / "data"
LABELS = HERE.parents[1] / "evaluation/labels/count_one.json"


def run(path: Path, checkpoint: str) -> dict:
    from beat_this.inference import Audio2Beats

    model = Audio2Beats(checkpoint, device="cpu", dbn=False)
    seen = {}

    def track(y, sr):
        b, d = model(y, sr)
        seen["beats"], seen["downbeats"] = np.asarray(b, float), np.asarray(d, float)
        return seen["beats"], seen["downbeats"]

    propose._track_beats = track
    y, sr = librosa.load(str(propose._extract_audio(path)), sr=22050, mono=True)
    g = propose.propose_grid(path, clip_duration_s=len(y) / sr)
    out = {k: v for k, v in asdict(g).items() if k != "alternates"}
    out["beats"] = [round(float(x), 3) for x in seen["beats"]]
    out["downbeats"] = [round(float(x), 3) for x in seen["downbeats"]]
    return out, len(y) / sr


def owner_label(bpm: float | None, one: float | None) -> dict | None:
    """The 2026-09 owner label for this lesson, matched on the shipped grid (the
    public labels file names clips, not jobs)."""
    if bpm is None:
        return None
    for lab in json.loads(LABELS.read_text())["labels"]:
        spc = 60 / lab["bpm"]
        if abs(lab["bpm"] - bpm) < 1.0 and abs((lab["count_one_s"] - one + spc / 2) % spc - spc / 2) < 0.07:
            return {"clip": lab["clip"], "count_one_s": lab["count_one_s"], "bpm": lab["bpm"]}
    return None


def main() -> None:
    queue = json.loads((DATA / "queue.json").read_text())["jobs"]
    rows = {}
    for j in queue:
        rows[j["job_id"]] = j
        for c in j["copies"]:
            rows[c["job_id"]] = {**c, "copy_of": j["job_id"], "credit": j.get("credit")}
    previous = {c["job_id"]: c for c in json.loads((DATA / "clips.json").read_text())} if (DATA / "clips.json").exists() else {}
    clips = []
    for mp4 in sorted((DATA / "media").glob("*.mp4")):
        job = mp4.stem
        row = rows.get(job, {})
        if job in previous:
            clips.append(previous[job])
            continue
        print(job, flush=True)
        final0, duration = run(mp4, "final0")
        small0, _ = run(mp4, "small0")
        shipped = None
        if row.get("bpm"):
            shipped = {"bpm": row["bpm"], "seconds_per_count": row["seconds_per_count"], "count_one_s": row["count_one_s"],
                       "count_one_alternates": row.get("count_one_alternates") or []}
        credit = row.get("credit") or {}
        clips.append({
            "job_id": job,
            "video": f"media/{mp4.name}",
            "duration_s": duration,
            "title": credit.get("creator") or credit.get("choreo") or job[4:12],
            "track": " — ".join(x for x in (credit.get("track"), credit.get("artist")) if x and x != "original sound") or None,
            "copy_of": row.get("copy_of"),
            "owner_label": owner_label(row.get("bpm"), row.get("count_one_s")),
            "candidates": {"shipped": shipped, "final0": final0, "small0": small0},
        })
        (DATA / "clips.json").write_text(json.dumps(clips, indent=1))
    (DATA / "clips.json").write_text(json.dumps(clips, indent=1))
    print(f"{len(clips)} clips -> {DATA / 'clips.json'}")


if __name__ == "__main__":
    main()
