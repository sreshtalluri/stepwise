# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Which ByteTrack ids are real dancers. Runs on pass 1's raw detections,
before any GPU reconstruction, so junk tracks cost nothing.

Measured on real TikToks (2026-09-23), three kinds of junk made it into
lessons as extra "dancers" under the old `>= 5 frames` rule:

- DUPLICATES / ID SWITCHES. RTMO sometimes emits two boxes for one body (a
  wide one that takes in the arms, a tight one) and ByteTrack gives each its
  own id, flipping between them: one solo dancer became tracks 1, 2 and 8.
  The two boxes only overlap IoU ~0.4-0.6, but their KEYPOINTS land on the
  same joints, which two different people's never do.
- BLIPS: a track alive for a handful of frames (a detection of a partial
  body, a passer-by's shoulder).
- REFLECTIONS: a dancer in front of a wall mirror; her reflection, small and
  seen between her legs, flickered in and out as three short tracks, each
  sitting entirely inside the dancer's own box.

clean_tracks() stitches the first kind into the surviving track (relabelling
its frames in place, so every later stage sees one id), then drops the rest.
Every decision is returned so the caller can log it (performance.json), never
shown to the learner.

Pure numpy, no CV/torch deps: unit-tested with synthetic tracks in
test_track_hygiene.py.
"""
from __future__ import annotations

import bisect

import numpy as np

# --- stitching ---------------------------------------------------------------
# A fragment joins a longer track when at least this share of its frames look
# like the same body as that track (per-frame tests below).
STITCH_MIN_MATCH_FRAC = 0.8
# Frame where both tracks are present: same body iff their mean keypoint
# distance is under this fraction of the longer track's box height. Measured:
# duplicate boxes on one body 0.002-0.019 (the solo TikTok, group-synced-01);
# two real dancers side by side never below 0.37 (group-synced-01, a duet).
DUP_MAX_KPT_DIST = 0.12
# Keypoints below this detector score are not compared.
KPT_MIN_SCORE = 0.3
# Frame where only the fragment is present: the longer track's nearest frame
# must be within this many seconds...
STITCH_MAX_GAP_S = 1.0
# ...its box centre within this many box heights of the fragment's...
STITCH_MAX_CENTER_DIST = 0.5
# ...and the two box heights within this ratio of each other.
STITCH_MAX_SCALE_RATIO = 1.5

# --- reflections / part detections -------------------------------------------
# Dropped if, on at least this share of its frames, a bigger track is present
# whose box contains at least CONTAINED_MIN_AREA of this one's box, and this
# one is at most CONTAINED_MAX_REL_HEIGHT of that bigger track's height.
# ponytail: geometry only. It catches a reflection seen THROUGH the dancer's
# silhouette however long it lasts, but not one standing BESIDE her (a side
# mirror, a mirror wall filmed at an angle): full size, never inside her box,
# there all clip. That needs a motion test -- per-frame limb angles of the two
# tracks, correlated with left/right swapped, near 1.0 at zero lag -- and a
# rule for which of the pair is real (larger, nearer the frame centre).
CONTAINED_MIN_FRAC = 0.7
CONTAINED_MIN_AREA = 0.8
CONTAINED_MAX_REL_HEIGHT = 0.6

# --- minimum presence ----------------------------------------------------------
# Kept if observed for at least max(PRESENCE_MIN_FRAC of the clip,
# PRESENCE_MIN_S)...
PRESENCE_MIN_FRAC = 0.15
PRESENCE_MIN_S = 2.0
# ...or, for a dancer who enters late or leaves early, if present for
# LATE_ENTRY_MIN_RUN_S in one stretch (gaps up to RUN_MAX_GAP_S don't break a
# stretch -- ByteTrack drops the odd frame) at a height of at least
# LATE_ENTRY_MIN_REL_HEIGHT of the biggest dancer.
LATE_ENTRY_MIN_RUN_S = 2.0
RUN_MAX_GAP_S = 0.5
LATE_ENTRY_MIN_REL_HEIGHT = 0.5


def _height(box) -> float:
    return max(1e-6, float(box[3] - box[1]))


def _center(box) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], dtype=np.float64)


def _kpt_dist(ka, kb) -> float:
    """Mean distance between keypoints both detections are confident about."""
    ka, kb = np.asarray(ka, np.float64), np.asarray(kb, np.float64)
    ok = np.ones(len(ka), bool)
    if ka.shape[-1] >= 3:
        ok &= (ka[:, 2] >= KPT_MIN_SCORE) & (kb[:, 2] >= KPT_MIN_SCORE)
    if ok.sum() < 4:
        return float("inf")
    return float(np.linalg.norm(ka[ok, :2] - kb[ok, :2], axis=1).mean())


def _contained(inner, outer) -> float:
    """Share of `inner`'s box area that lies inside `outer`."""
    w = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    h = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = max(1e-6, float((inner[2] - inner[0]) * (inner[3] - inner[1])))
    return w * h / area


def _continues(ab, bb) -> bool:
    """Could box bb be the same body as box ab, seen a moment apart?"""
    ratio = _height(ab) / _height(bb)
    return bool(np.linalg.norm(_center(ab) - _center(bb)) <= STITCH_MAX_CENTER_DIST * _height(ab)
                and 1 / STITCH_MAX_SCALE_RATIO <= ratio <= STITCH_MAX_SCALE_RATIO)


def _match_frac(a: dict, b: dict, max_gap: int) -> float:
    """Share of b's frames on which b is the same body as track a.

    Frames where both exist: a duplicate box (same keypoints). Stretches where
    only b exists: a hand-over -- a's last frame before the stretch (or first
    after it) is within max_gap frames and continuous in position and scale.
    """
    a_frames = sorted(a)
    hits = 0
    stretch: list[int] = []

    def close(stretch):
        if not stretch:
            return 0
        i = bisect.bisect_left(a_frames, stretch[0])
        before = a_frames[i - 1] if i > 0 else None
        after = a_frames[i] if i < len(a_frames) else None
        ok = ((before is not None and stretch[0] - before <= max_gap
               and _continues(a[before][0], b[stretch[0]][0]))
              or (after is not None and after - stretch[-1] <= max_gap
                  and _continues(a[after][0], b[stretch[-1]][0])))
        return len(stretch) if ok else 0

    for f in sorted(b):
        if f in a:
            hits += close(stretch)
            stretch = []
            ab, ak = a[f]
            hits += _kpt_dist(ak, b[f][1]) <= DUP_MAX_KPT_DIST * _height(ab)
        elif stretch and (f - stretch[-1] > max_gap
                          or bisect.bisect_left(a_frames, f) != bisect.bisect_right(a_frames, stretch[-1])):
            hits += close(stretch)
            stretch = [f]
        else:
            stretch.append(f)
    hits += close(stretch)
    return hits / max(1, len(b))


def _longest_run(frames, max_gap: int) -> int:
    """Longest stretch in frames (first to last, inclusive), bridging gaps <= max_gap."""
    frames = sorted(frames)
    start, best = frames[0], 1
    for prev, cur in zip(frames, frames[1:]):
        if cur - prev > max_gap + 1:
            start = cur
        best = max(best, cur - start + 1)
    return best


def clean_tracks(raw_detections: list, fps: float, min_frames: int = 5) -> tuple[list[int], list[dict]]:
    """Returns (dancer_track_ids, decisions). Stitched fragments are relabelled
    IN PLACE in raw_detections[i]["track_ids"] on the frames where the
    surviving track is absent; on frames where both are present the fragment
    keeps its own id (it is a duplicate box there, and is not a dancer).

    `min_frames` is the old CONFIDENT_MIN_FRAMES floor, kept as the floor for
    the one guard below: the longest track is never dropped for presence, so a
    clip that had a dancer before this stage still has one after it.
    """
    n_frames = len(raw_detections)
    tracks: dict[int, dict] = {}
    for i, det in enumerate(raw_detections):
        for box, kps, tid in zip(det["boxes"], det["keypoints"], np.asarray(det["track_ids"]).tolist()):
            tracks.setdefault(int(tid), {})[i] = (np.asarray(box), np.asarray(kps))
    decisions: list[dict] = []

    # 1. Stitch, longest first, so fragments fold into the track that
    # carries the most evidence and that track's id survives.
    max_gap = max(1, round(STITCH_MAX_GAP_S * fps))
    survivors: list[int] = []
    for tid in sorted(tracks, key=lambda t: (-len(tracks[t]), t)):
        best, best_frac = None, 0.0
        for sid in survivors:
            frac = _match_frac(tracks[sid], tracks[tid], max_gap)
            if frac > best_frac:
                best, best_frac = sid, frac
        if best is None or best_frac < STITCH_MIN_MATCH_FRAC:
            survivors.append(tid)
            continue
        moved = [f for f in tracks[tid] if f not in tracks[best]]
        for f in moved:
            tracks[best][f] = tracks[tid][f]
            ids = np.asarray(raw_detections[f]["track_ids"])
            raw_detections[f]["track_ids"] = np.where(ids == tid, best, ids).astype(ids.dtype)
        decisions.append({"track": tid, "action": "stitched", "into": best,
                          "frames_moved": len(moved), "frames_duplicate": len(tracks[tid]) - len(moved),
                          "match_frac": round(best_frac, 3)})

    heights = {t: float(np.median([_height(b) for b, _ in tracks[t].values()])) for t in survivors}
    longest = max(survivors, key=lambda t: len(tracks[t]), default=None)
    kept: list[int] = []
    for tid in survivors:
        tr = tracks[tid]
        # 2. Reflection / part-of-another-body: small and sitting inside a
        # bigger track's box most of the time it exists.
        inside = sum(
            any(_contained(tr[f][0], tracks[o][f][0]) >= CONTAINED_MIN_AREA
                and _height(tr[f][0]) <= CONTAINED_MAX_REL_HEIGHT * _height(tracks[o][f][0])
                for o in survivors if o != tid and f in tracks[o])
            for f in tr)
        if tid != longest and inside >= CONTAINED_MIN_FRAC * len(tr):
            decisions.append({"track": tid, "action": "dropped", "reason": "inside_another_dancer",
                              "frames": len(tr), "frames_inside": inside})
            continue

        # 3. Minimum presence, with the late-entry exemption.
        run = _longest_run(tr, max(0, round(RUN_MAX_GAP_S * fps)))
        rel_h = heights[tid] / max(heights.values())
        if len(tr) >= max(PRESENCE_MIN_FRAC * n_frames, PRESENCE_MIN_S * fps):
            kept.append(tid)
        elif run >= LATE_ENTRY_MIN_RUN_S * fps and rel_h >= LATE_ENTRY_MIN_REL_HEIGHT:
            kept.append(tid)
        elif tid == longest and len(tr) >= min_frames:
            kept.append(tid)  # never leave a clip with no dancer
        else:
            decisions.append({"track": tid, "action": "dropped", "reason": "too_brief",
                              "frames": len(tr), "longest_run_frames": run,
                              "rel_height": round(rel_h, 3)})
    return sorted(kept), decisions
