"""Early results a job can show before it succeeds (the flow redesign).

Two things the processing screen uses to make the wait useful:

1. `counts_milestone(grid)`: the beat proposal, trimmed to what the screen
   needs to draw the count strip on the raw video. It becomes JobStatus
   `milestones.counts` (job-status.schema.json). A PROPOSAL, same as the
   lesson's; the screen does not present it as more than that.

2. `build_detections(...)`: `{clip_id}.detections.json`, the detector's 2D pass,
   drawn over the learner's own clip while the 3D is still being built. It is
   the raw RTMO+ByteTrack output that already exists after process_clip's pass
   1 and was until now kept only inside the final npz. Nothing here is
   estimated: these are the detector's own keypoints, so drawing them makes no
   §7h claim beyond "this is what the detector saw in this frame".

   Shape (every coordinate normalised to [0, 1] against the frame):

       {"fps": 5.0, "width": 720, "height": 1280, "times": [t0, t1, ...],
        "dancers": [{"id": 3, "points": [frame, ...]}]}

   where each `frame` is null (the dancer was not detected in that sample) or a
   list of 17 COCO keypoints, each [x, y] or null when the detector's own score
   for it was below MIN_SCORE. Only confidently-tracked dancers are kept, the
   same set pass 2 reconstructs, so a one-frame false detection never gets a
   skeleton. ~60 KB per dancer for a 60 s clip.

Plain python, no numpy, so both api.py and the GPU worker import it and it is
unit-testable anywhere.
"""
from __future__ import annotations

MIN_SCORE = 0.3
TARGET_FPS = 5.0


def counts_milestone(grid: dict | None) -> dict | None:
    """beat_detect.ProposedGrid (as a dict) -> JobStatus milestones.counts."""
    if not grid or not grid.get("seconds_per_count", 0) > 0:
        return None
    return {
        "bpm": round(float(grid["bpm"]), 2),
        "count_one_s": round(float(grid["count_one_s"]), 4),
        "seconds_per_count": round(float(grid["seconds_per_count"]), 5),
        "confidence": round(float(grid.get("confidence") or 0.0), 3),
    }


def build_detections(sample_times_s, raw_detections, confident_track_ids,
                     frame_width: int, frame_height: int, target_fps: float = TARGET_FPS) -> dict:
    times = [float(t) for t in sample_times_s]
    src_fps = (len(times) - 1) / max(1e-6, times[-1] - times[0]) if len(times) > 1 else target_fps
    step = max(1, round(src_fps / target_fps))
    idx = list(range(0, len(times), step))
    w, h = max(1, frame_width), max(1, frame_height)
    ids = sorted(int(t) for t in confident_track_ids)
    dancers = {tid: [] for tid in ids}

    for i in idx:
        det = raw_detections[i]
        by_id = {int(tid): det["keypoints"][n] for n, tid in enumerate(list(det["track_ids"]))}
        for tid in ids:
            kp = by_id.get(tid)
            dancers[tid].append(None if kp is None else [
                [round(float(p[0]) / w, 3), round(float(p[1]) / h, 3)]
                if len(p) < 3 or float(p[2]) >= MIN_SCORE else None
                for p in kp
            ])

    return {
        "fps": round(src_fps / step, 3),
        "width": frame_width,
        "height": frame_height,
        "times": [round(times[i], 3) for i in idx],
        "dancers": [{"id": tid, "points": dancers[tid]} for tid in ids],
    }
