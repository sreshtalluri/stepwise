# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for hand_crops.py.

No GPU, torch, weights, or video -- synthetic detections with hand-placed
keypoints, so every branch that can emit a WRONG rectangle (a low-confidence
wrist, a hand out of frame, two hands too far apart to share one crop) is
asserted to emit None instead, and the contract's [0,1] bounds are checked
against the schema's own rules.

Run: python tools/test_hand_crops.py   (or pytest)
"""
import json
from pathlib import Path

import numpy as np

from hand_crops import (
    HAND_POSE_CEILING,
    MIN_KEYPOINT_CONF,
    annotate_clip,
    hand_pose_confidence,
    side_crop_rects,
)

W, H = 576, 1024  # the real source size (evaluation/clips.yaml RESOLUTION FINDING)


def _det(lw=(200, 500, 0.9), rw=(300, 500, 0.9), la=(240, 900, 0.9), ra=(280, 900, 0.9),
         box=(150, 200, 400, 950), tid=4):
    k = np.zeros((1, 17, 3), dtype=np.float32)
    k[0, 9], k[0, 10], k[0, 15], k[0, 16] = lw, rw, la, ra
    return {"keypoints": k, "boxes": np.array([box], dtype=np.float32),
            "track_ids": np.array([tid])}


# 120 px boxes: the measured median hand-crop size on solo-01/solo-07.
def _person(lb=(140, 440, 260, 560), rb=(240, 440, 360, 560)):
    return {"lhand_bbox": np.array(lb, dtype=np.float64),
            "rhand_bbox": np.array(rb, dtype=np.float64),
            "bone_length_confidence": np.ones(127, dtype=np.float32)}


def _in_unit(r):
    """Exactly the schema's CropRect constraints (motion-result.schema.json)."""
    assert set(r) == {"x", "y", "width", "height"}, r
    assert 0.0 <= r["x"] <= 1.0 and 0.0 <= r["y"] <= 1.0, r
    assert 0.0 < r["width"] <= 1.0 and 0.0 < r["height"] <= 1.0, r
    # json.dumps must work on this verbatim -- numpy scalars would not serialize.
    assert all(type(v) is float for v in r.values()), r
    json.dumps(r)


def test_normal_frame_emits_both_rects_in_unit_range():
    pf = [{4: _person()}]
    rep = annotate_clip(pf, [_det()], [4], W, H)
    assert rep[4] == {"n_frames": 1, "n_hand_rects": 1, "n_foot_rects": 1}
    _in_unit(pf[0][4]["hand_crop_rect"])
    _in_unit(pf[0][4]["foot_crop_rect"])
    # The rect must actually contain the wrists it claims to crop.
    r = pf[0][4]["hand_crop_rect"]
    assert r["x"] * W <= 200 and (r["x"] + r["width"]) * W >= 300


def test_low_confidence_wrists_give_no_hand_rect_and_zero_confidence():
    """Below MIN_KEYPOINT_CONF the estimator centres its hand box on the BODY,
    so a rect here would be a rectangle of torso labelled 'hands'."""
    pf = [{4: _person()}]
    d = _det(lw=(200, 500, 0.05), rw=(300, 500, 0.05))
    annotate_clip(pf, [d], [4], W, H)
    assert pf[0][4]["hand_crop_rect"] is None
    assert list(pf[0][4]["hand_confidence"]) == [0.0, 0.0]
    assert pf[0][4]["foot_crop_rect"] is not None  # feet are unaffected


def test_hands_too_far_apart_cannot_share_one_crop():
    """The contract's `hands` is ONE rect for both hands. When they are at
    opposite ends of the frame that one rect magnifies nothing, so null is the
    honest answer -- but the per-hand POSE confidence is a separate claim and
    still stands."""
    pf = [{4: _person(lb=(20, 40, 140, 160), rb=(430, 860, 550, 980))}]
    d = _det(lw=(80, 100, 0.9), rw=(490, 920, 0.9))
    annotate_clip(pf, [d], [4], W, H)
    assert pf[0][4]["hand_crop_rect"] is None
    assert pf[0][4]["hand_confidence"].max() > 0


def test_out_of_frame_region_is_null_not_a_clamped_sliver():
    pf = [{4: _person(lb=(-220, 440, -100, 560), rb=(-215, 445, -95, 565))}]
    d = _det(lw=(-100, 500, 0.9), rw=(-95, 505, 0.9))
    annotate_clip(pf, [d], [4], W, H)
    assert pf[0][4]["hand_crop_rect"] is None


def test_one_visible_hand_still_gets_a_crop():
    pf = [{4: _person()}]
    d = _det(lw=(200, 500, 0.05))  # left wrist unseen, right one fine
    annotate_clip(pf, [d], [4], W, H)
    assert pf[0][4]["hand_crop_rect"] is not None
    assert pf[0][4]["hand_confidence"][0] == 0.0
    assert pf[0][4]["hand_confidence"][1] > 0.0


def test_absent_frames_and_unknown_tracks_are_left_alone():
    pf = [{}, {4: _person()}, {9: _person()}]
    rep = annotate_clip(pf, [_det(), _det(), _det(tid=9)], [4], W, H)
    assert pf[0] == {} and "hand_crop_rect" not in pf[2][9]
    assert rep[4]["n_frames"] == 1


def test_confidence_is_capped_by_the_measured_ceiling():
    """However good the evidence, the finger POSE cannot be better than the
    model that produced it -- see hand_crops.py's measurements."""
    assert hand_pose_confidence(1.0, 10_000.0, 1.0) == HAND_POSE_CEILING
    assert hand_pose_confidence(MIN_KEYPOINT_CONF, 500.0, 1.0) == 0.0
    assert hand_pose_confidence(1.0, 20.0, 1.0) == 0.0          # hand too small to see
    assert hand_pose_confidence(1.0, 500.0, 0.0) == 0.0         # arm chain untrustworthy
    assert 0 < hand_pose_confidence(1.0, 110.0, 1.0) < HAND_POSE_CEILING


def test_wrist_joint_indices_match_the_hierarchy_json():
    """The default wrist_joint_idx must stay pinned to the real skeleton, or the
    confidence reads some other joint's chain error."""
    p = Path(__file__).resolve().parents[3] / "mhr_joint_hierarchy.json"
    names = [j["name"] for j in json.loads(p.read_text())["joints"]]
    assert (names.index("l_wrist"), names.index("r_wrist")) == (78, 42)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


def test_side_rects_are_sized_from_their_own_limb_and_gated_on_their_own_joint():
    """Each side's rect is centred on its own wrist/ankle and sized from its own
    forearm/shank, not the body box; an unseen wrist nulls only its own side."""
    d = _det(lw=(80, 300, 0.9), rw=(490, 920, 0.2))
    k = d["keypoints"][0]
    k[7] = (80, 420, 0.9)    # left elbow 120 px below the left wrist -> hand ~90 px
    k[8] = (490, 800, 0.9)   # right elbow fine, but the right wrist itself is unseen
    k[13] = (240, 800, 0.1)  # left knee unseen -> left foot falls back to the floor size
    out = side_crop_rects([d, {"keypoints": k[None], "boxes": d["boxes"], "track_ids": np.array([9])}], 4, W, H)
    assert set(out) == {"left_hand", "right_hand", "left_foot", "right_foot"}
    assert all(len(v) == 2 for v in out.values())
    assert all(v[1] is None for v in out.values())  # other track only on frame 2
    lh = out["left_hand"][0]
    _in_unit(lh)
    assert out["right_hand"][0] is None  # no wrist, no rect
    # Half-side = 0.75 * 120 = 90 px, padded 1.25x -> 225 px square around (80, 300),
    # clipped at the frame's left edge, so width = 80 + 112.5.
    assert abs(lh["height"] * H - 225) < 1 and abs(lh["width"] * W - 192.5) < 1
    # Left foot: knee unseen -> floor = body-box hand size / 2 = ((250+750)/2/3)/2.
    lf = out["left_foot"][0]
    assert abs(lf["height"] * H - 2 * 1.25 * (500 / 3 / 2)) < 1
    _in_unit(out["right_foot"][0])
