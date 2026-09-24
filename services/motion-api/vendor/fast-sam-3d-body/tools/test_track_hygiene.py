# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Synthetic track sets for track_hygiene.clean_tracks. Each case is a shape
measured on a real clip (see track_hygiene.py's docstring). Run:
python tools/test_track_hygiene.py (or pytest)."""
import numpy as np

from track_hygiene import clean_tracks

FPS = 15
RNG = np.random.default_rng(0)
# 17 COCO-ish keypoints as fractions of a box (x, y).
TEMPLATE = np.stack([RNG.uniform(0.2, 0.8, 17), np.linspace(0.05, 0.95, 17)], axis=1)


def body(x, y=100.0, h=500.0, jitter=0.0):
    """A detection of a body whose box top-left is (x, y), height h."""
    w = 0.4 * h
    box = np.array([x, y, x + w, y + h], np.float32)
    kps = np.concatenate([TEMPLATE * [w, h] + [x, y] + RNG.normal(0, jitter, (17, 2)),
                          np.full((17, 1), 0.9)], axis=1).astype(np.float32)
    return box, kps


def clip(n_frames, dets):
    """dets: {frame: [(track_id, (box, kps)), ...]} -> raw_detections."""
    out = []
    for i in range(n_frames):
        items = dets.get(i, [])
        out.append({
            "boxes": np.array([b for _, (b, _) in items], np.float32).reshape(-1, 4),
            "keypoints": np.array([k for _, (_, k) in items], np.float32).reshape(-1, 17, 3),
            "track_ids": np.array([t for t, _ in items], np.int64),
        })
    return out


def add(dets, tid, frames, make):
    for f in frames:
        dets.setdefault(f, []).append((tid, make(f)))


def test_split_track_is_stitched_and_relabelled():
    # One dancer, ByteTrack loses her for 5 frames and re-finds her as id 8.
    dets = {}
    add(dets, 2, range(0, 300), lambda f: body(100 + f * 0.2))
    add(dets, 8, range(305, 450), lambda f: body(100 + f * 0.2))
    raw = clip(450, dets)
    kept, decisions = clean_tracks(raw, FPS)
    assert kept == [2]
    assert decisions[0]["action"] == "stitched" and decisions[0]["into"] == 2
    assert all(set(d["track_ids"].tolist()) <= {2} for d in raw)


def test_duplicate_box_on_same_body_is_stitched():
    # RTMO's wide+tight double box: same keypoints, both ids alive, flipping.
    dets = {}
    add(dets, 2, [f for f in range(300) if f % 7], lambda f: body(100, jitter=2))
    add(dets, 1, range(0, 300, 3), lambda f: body(100, jitter=2))
    raw = clip(300, dets)
    kept, decisions = clean_tracks(raw, FPS)
    assert kept == [2]
    (d,) = decisions
    assert d["track"] == 1 and d["frames_moved"] > 0 and d["frames_duplicate"] > 0
    # A frame that had only the duplicate now carries the survivor's id.
    assert raw[0]["track_ids"].tolist() == [2]


def test_blip_is_dropped():
    dets = {}
    add(dets, 1, range(300), lambda f: body(100))
    add(dets, 7, range(40, 45), lambda f: body(400))
    kept, decisions = clean_tracks(clip(300, dets), FPS)
    assert kept == [1]
    assert decisions == [{"track": 7, "action": "dropped", "reason": "too_brief", "frames": 5,
                          "longest_run_frames": 5, "rel_height": 1.0}]


def test_flickering_reflection_inside_dancer_is_dropped():
    # Mirror behind the dancer: a small figure between her legs, 3 short tracks.
    dets = {}
    add(dets, 1, range(216), lambda f: body(150, h=760))
    for tid, frames in ((2, range(22, 32)), (3, range(73, 82)), (6, range(158, 164))):
        add(dets, tid, frames, lambda f: body(330, y=740, h=120))
    kept, decisions = clean_tracks(clip(216, dets), FPS)
    assert kept == [1]
    assert {d["track"]: d["reason"] for d in decisions} == {
        2: "inside_another_dancer", 3: "inside_another_dancer", 6: "inside_another_dancer"}


def test_two_real_dancers_side_by_side_are_both_kept():
    dets = {}
    add(dets, 1, range(450), lambda f: body(100, jitter=3))
    add(dets, 2, range(450), lambda f: body(100 + 0.45 * 500, jitter=3))  # half a body over
    kept, decisions = clean_tracks(clip(450, dets), FPS)
    assert kept == [1, 2] and decisions == []


def test_second_dancer_losing_track_next_to_first_is_not_absorbed():
    # Dancer 2's track breaks (id 2 -> 5) while dancer 1 stays tracked beside her.
    dets = {}
    add(dets, 1, range(450), lambda f: body(100))
    add(dets, 2, range(0, 200), lambda f: body(400))
    add(dets, 5, range(203, 450), lambda f: body(400))
    kept, decisions = clean_tracks(clip(450, dets), FPS)
    assert kept == [1, 5] or kept == [1, 2]
    assert [d["into"] for d in decisions] in ([5], [2])


def test_late_entering_dancer_present_3s_is_kept():
    # 40 s clip; a second dancer walks on for the last 3 s (7.5% of the clip).
    dets = {}
    add(dets, 1, range(600), lambda f: body(100))
    add(dets, 4, range(555, 600), lambda f: body(400, h=450))
    kept, _ = clean_tracks(clip(600, dets), FPS)
    assert kept == [1, 4]


def test_small_background_figure_for_3s_is_dropped():
    # Same 3 s, but a far-away bystander at a quarter of the dancer's height.
    dets = {}
    add(dets, 1, range(600), lambda f: body(100))
    add(dets, 4, range(555, 600), lambda f: body(400, h=120))
    kept, decisions = clean_tracks(clip(600, dets), FPS)
    assert kept == [1] and decisions[0]["reason"] == "too_brief"


def test_clip_never_loses_its_only_dancer():
    # Dancer barely on camera (1 s of a 20 s clip): still the lesson's dancer.
    dets = {}
    add(dets, 3, range(100, 115), lambda f: body(100))
    kept, _ = clean_tracks(clip(300, dets), FPS)
    assert kept == [3]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
