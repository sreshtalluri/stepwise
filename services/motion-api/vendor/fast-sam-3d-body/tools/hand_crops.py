# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Hand/foot video-crop rectangles, and an honest per-hand confidence.

WHY THIS EXISTS AS A CROP AND NOT AS BETTER 3D FINGERS
------------------------------------------------------
Measured on the real `solo-01.npz` (291 frames, track 4) and `solo-07.npz`
(353 frames, track 1) in Modal Volume `stepwise-results`, plus the matching
576x1024 source clips in `stepwise-eval`:

1. MHR's finger joints barely articulate. Taking each joint's LOCAL
   (parent-relative) rotation and measuring the full angular span over a whole
   clip:

       joint            solo-01 span   solo-07 span
       shoulder            170 deg        137 deg
       elbow               146 deg        132 deg
       knee                125 deg        147 deg
       wrist                80 deg         94 deg
       finger knuckles      23 deg (med)   22 deg (med), 42 deg max

   Open-hand to fist is ~90 deg at every knuckle. The model explores roughly a
   quarter of that, and never reaches either end. NOTE for anyone re-checking
   this: `skel_state`'s quaternion block is the joint's GLOBAL rotation (it
   converts exactly to `pred_global_rots`, max abs difference 6e-8), so raw
   per-frame deltas on those channels are dominated by arm motion and make the
   fingers look like they are moving 34 deg/frame. They are not; that is the
   wrist carrying them. Compose with the parent's inverse first.

2. Against independent evidence the finger pose is near-noise. Running an
   independent 2D hand landmarker over the estimator's OWN hand crops from the
   real footage, and comparing scale/rotation-free hand-shape descriptors:

       Procrustes RMS between the two, matched frames    0.889 / 0.984
       ... the same comparison on SHUFFLED frame pairs   0.939 / 0.982
       per-finger curl correlation                       +0.30 .. +0.49
                                    (shuffled-null p95)   0.09 .. 0.12

   Matched frames are indistinguishable from randomly paired ones on whole-hand
   shape. Per-finger curl does carry a real but weak signal (r ~ 0.4, i.e. ~16%
   of variance). MHR's curl never goes below 0.50 (1.0 = straight); the
   landmarker's reaches 0.23. MHR does not make fists.

3. A dedicated hand model does not fix it at this source resolution, so none is
   added. The landmarker found a hand in only 69% / 66% of crops, its own
   frame-to-frame curl jump (0.14-0.18) is more than half its entire spread
   (0.26), and it mislabelled which hand it was looking at in 20-34% of crops --
   at EVERY crop size from 60px to 220px, so this is motion blur and source
   compression, not pixel count. Retargeting that onto MHR's finger chains would
   trade a flat wrong hand for a jittery, sometimes-mirrored wrong hand. See
   docs/GATE-REPORT.md's hands addendum for the full four-axis licence read.

So: the 3D hand stays as it is and is reported as low confidence, and the
learner is shown the actual pixels. That is `evaluation/clips.yaml`'s
`stress-hands` EXPECTED OUTCOME reached by measurement rather than assumption.

WHAT THIS MODULE PRODUCES
-------------------------
Per person per frame, attached to the `process_clip` per-frame dicts exactly
like `skeleton_constraints.constrain_clip` attaches `bone_length_confidence`:

    hand_crop_rect   contract CropRect (normalized [0,1]) or None
    foot_crop_rect   contract CropRect (normalized [0,1]) or None
    hand_confidence  (2,) float32, [left, right], in [0, 1]

and, separately, `side_crop_rects`: one rect per hand and per foot, computed
at MotionResult assembly from the npz's stored detections (see SIDE_LIMBS).

Rectangles come from the DETECTOR's wrist/ankle keypoints, not from MHR's
reprojected ones. That is a measured choice too: MHR's reprojected ankles sit
51.8 px (p90 106 px) from the detector's ankles on solo-01 and 33.5 px
(p90 69.6) on solo-07 -- a crop built from them would routinely miss the foot.
The detector keypoints are the direct image evidence and carry their own
confidence, which is also what decides whether a rect may be emitted at all.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

# COCO-17 indices. `to_openpose=False` keeps these (tools/rtmo_detector.py).
L_WRIST, R_WRIST, L_ANKLE, R_ANKLE = 9, 10, 15, 16

# Below this the vendor's own `_get_hand_box_from_yolo_pose` stops trusting the
# wrist and centres the hand box on the BODY instead (sam3d_body.py ~line 3480).
# A rect emitted from that fallback would be a rectangle of torso labelled
# "hands", so the same threshold gates emission here. Measured fallback rate:
# 3.6% of hand-frames on solo-01 track 4, 0.8% on solo-07 track 1, but 41.7% on
# solo-07's small background dancer (track 3) -- it is not a rare case.
MIN_KEYPOINT_CONF = 0.3

# Box side = (body_width + body_height) / 2 / SCALE, the vendor's hand_box_scale
# rule, reused for feet so both crops are sized the same way.
BOX_SCALE = 3.0

# Breathing room so the crop is watchable rather than a tight bound.
PAD = 1.25

# The contract's `hands` field is ONE rect for both hands (v1 does not split
# left/right), so it needs a rule for when two hands cannot share a crop. The
# rule is the crop's own purpose: a crop exists to MAGNIFY. At 0.25 of the frame
# area the learner still gets 2x linear magnification over the full frame; above
# that the "crop" is just the video again and null is the honest answer.
# Measured union areas on solo-01/solo-07: median 0.056-0.071, p90 0.108-0.145,
# max 0.335 -- so this keeps 99.2-99.3% of frames where a wrist was seen and
# rejects only the genuinely spread-eagled ones.
MAX_CROP_FRAME_FRAC = 0.25

# The ceiling from measurement 2 above: per-finger curl correlates r ~ 0.3-0.49
# with independent evidence, i.e. r^2 ~ 0.09-0.24 of the real hand-shape
# variance. No amount of good wrist localization makes the finger POSE better
# than the model that produced it, so confidence is capped here whatever the
# other evidence says. This is deliberately low enough that any sane suppression
# threshold renders hands `uncertain` (docs/DESIGN.md section 4). Raise it only
# with a new measurement, not a new feeling.
HAND_POSE_CEILING = 0.25

# Effective resolution of the hand crop. The independent landmarker found
# nothing at all below ~60 px and was reliable around ~160 px; between those it
# degrades smoothly, so confidence does too.
MIN_HAND_CROP_PX, GOOD_HAND_CROP_PX = 60.0, 160.0


def _rect(boxes: Sequence[np.ndarray], frame_w: int, frame_h: int) -> Optional[dict]:
    """Union of xyxy pixel boxes -> one normalized contract CropRect, or None.

    Normalized against the frame dimensions `process_clip` read back off the
    extracted frames, which are post-rotation (ffmpeg applies the display matrix
    during extraction), so this matches CropRect's "relative to source_video
    width_px/height_px AFTER rotation_deg is applied".

    Returns None rather than a clamped sliver when the region is essentially
    outside the frame -- a rect is a claim that there is something to look at.
    """
    if not boxes or frame_w <= 0 or frame_h <= 0:
        return None
    b = np.asarray(boxes, dtype=np.float64)
    x0, y0, x1, y1 = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * PAD, (y1 - y0) * PAD
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    cx0, cy0 = max(x0, 0.0), max(y0, 0.0)
    cx1, cy1 = min(x1, float(frame_w)), min(y1, float(frame_h))
    if cx1 - cx0 <= 1.0 or cy1 - cy0 <= 1.0:
        return None  # out of frame, or degenerate
    # Less than a third of the padded region actually visible: not a crop worth
    # showing, and pretending otherwise would put a mostly-empty box on screen.
    if (cx1 - cx0) * (cy1 - cy0) < 0.33 * w * h:
        return None
    if (cx1 - cx0) * (cy1 - cy0) > MAX_CROP_FRAME_FRAC * frame_w * frame_h:
        return None  # too big to magnify anything -- see MAX_CROP_FRAME_FRAC
    # Plain floats, not np.float64: this dict is handed to the JSON contract
    # verbatim, and the stdlib encoder does not know numpy scalars.
    return {
        "x": float(cx0 / frame_w),
        "y": float(cy0 / frame_h),
        "width": float((cx1 - cx0) / frame_w),
        "height": float((cy1 - cy0) / frame_h),
    }


def _box_side(body_box: np.ndarray) -> float:
    return float((body_box[2] - body_box[0] + body_box[3] - body_box[1]) / 2 / BOX_SCALE)


def hand_pose_confidence(wrist_conf: float, crop_px: float, chain_conf: float = 1.0) -> float:
    """Confidence in this hand's 3D FINGER POSE (not in the crop rectangle).

    Weakest link of three, then capped: how well the wrist was localized (a
    wrist the detector did not see means the hand crop was the torso), how many
    pixels of hand the model actually had, and how much the arm carrying the
    hand was itself corrected (skeleton_constraints' per-joint
    `bone_length_confidence` at the wrist -- a hand hanging off a shoulder the
    model got wrong is not trustworthy because its own knuckles looked fine).

    `min` rather than a product, for the same reason skeleton_constraints takes
    the worst error along a chain: three multiplied 0-1 terms collapse toward
    zero and stop being readable, while the weakest link is exactly the thing a
    suppression stage wants to know about.
    """
    if not np.isfinite(wrist_conf) or wrist_conf <= MIN_KEYPOINT_CONF:
        return 0.0
    localization = min((wrist_conf - MIN_KEYPOINT_CONF) / (0.8 - MIN_KEYPOINT_CONF), 1.0)
    resolution = (crop_px - MIN_HAND_CROP_PX) / (GOOD_HAND_CROP_PX - MIN_HAND_CROP_PX)
    resolution = min(max(resolution, 0.0), 1.0)
    chain = chain_conf if np.isfinite(chain_conf) else 0.0
    return float(HAND_POSE_CEILING * min(localization, resolution, chain))


# ---- per-side crops ----------------------------------------------------------
# One rect per hand and per foot, sized from THAT limb, not the body box. RTMO
# is COCO-17, so the detector has no finger or toe points; the nearest honest
# measure of a hand's pixel extent is its own forearm (elbow->wrist), and of a
# foot's its own shank (knee->ankle). Anthropometric ratios (Drillis & Contini
# segment lengths as fractions of stature): hand 0.108 / forearm 0.146 ~= 0.75,
# foot 0.152 / shank 0.246 ~= 0.62. The square is centred on the wrist/ankle
# with a half-side of one hand/foot length, so the hand fits whichever way it
# points; `_rect` then adds PAD.
#
# Foreshortening (forearm pointed at the camera) shrinks the measured length,
# so it is floored at half the vendor's body-box hand size -- a floor, not the
# size. The viewer sizes its steady crop off the p90 of these per clip anyway
# (apps/web/lib/motion.ts steadyCropTrack), so a foreshortened frame does not
# zoom the close-up in.
# ponytail: MHR's own 2D finger/toe keypoints (pred_keypoints_2d) would give a
# per-frame extent, but they reproject 30-50 px off the detector at 576x1024
# (see the header) -- about a whole hand -- so they are not used for this.
COCO_L_ELBOW, COCO_R_ELBOW, COCO_L_KNEE, COCO_R_KNEE = 7, 8, 13, 14
SIDE_LIMBS = {
    # region: (end keypoint, proximal keypoint, limb-end length / proximal segment)
    "left_hand": (L_WRIST, COCO_L_ELBOW, 0.75),
    "right_hand": (R_WRIST, COCO_R_ELBOW, 0.75),
    "left_foot": (L_ANKLE, COCO_L_KNEE, 0.62),
    "right_foot": (R_ANKLE, COCO_R_KNEE, 0.62),
}


def side_rect(kpts: np.ndarray, body_box: Optional[np.ndarray], region: str,
              frame_w: int, frame_h: int) -> Optional[dict]:
    """One hand's or foot's CropRect from COCO-17 keypoints (x, y, conf), or None.

    None when the wrist/ankle itself is not confidently seen -- same gate as the
    combined rects, for the same reason (below it there is nothing to centre on).
    """
    end, prox, ratio = SIDE_LIMBS[region]
    if kpts[end, 2] <= MIN_KEYPOINT_CONF:
        return None
    floor = _box_side(body_box) / 2 if body_box is not None else 0.0
    half = floor
    if kpts[prox, 2] > MIN_KEYPOINT_CONF:
        half = max(ratio * float(np.hypot(*(kpts[end, :2] - kpts[prox, :2]))), floor)
    cx, cy = float(kpts[end, 0]), float(kpts[end, 1])
    return _rect([np.array([cx - half, cy - half, cx + half, cy + half])], frame_w, frame_h)


def side_crop_rects(raw_detections: Sequence[dict], track_id: int,
                    frame_w: int, frame_h: int) -> dict:
    """{region: [CropRect | None] per sample} for the four SIDE_LIMBS regions.

    Pure numpy off the detector output the npz already stores, so it runs at
    MotionResult assembly (motion_result.py) for new and already-reconstructed
    lessons alike -- no GPU, no re-reconstruction, as long as the npz exists.
    """
    out = {region: [] for region in SIDE_LIMBS}
    for det in raw_detections:
        kpts = box = None
        if isinstance(det, dict):
            m = np.nonzero(np.asarray(det["track_ids"]) == track_id)[0]
            if len(m):
                kpts = np.asarray(det["keypoints"][m[0]])
                box = np.asarray(det["boxes"][m[0]]) if "boxes" in det else None
        for region in SIDE_LIMBS:
            out[region].append(None if kpts is None else side_rect(kpts, box, region, frame_w, frame_h))
    return out


def annotate_clip(
    per_frame: Sequence[dict],
    raw_detections: Sequence[dict],
    track_ids: Sequence[int],
    frame_width: int,
    frame_height: int,
    wrist_joint_idx: tuple = (78, 42),  # (l_wrist, r_wrist) in mhr_joint_hierarchy.json
) -> dict:
    """Attach crop rects and hand confidence in place; return per-track counts.

    Left/right here is the detector's COCO convention throughout: COCO index 9
    is the person's left wrist, and `lhand_bbox` is built from it, so a rect
    derived from `lhand_bbox` really is the person's left hand. (Careful if you
    extend this using `sam_3d_body/metadata/mhr70.py`: the two WRIST entries in
    that name list are swapped relative to the rest of the skeleton -- verified
    on both clips, its "left-wrist" sits 0.11 m from the 127-joint skeleton's
    r_wrist and 0.56 m from l_wrist, while every elbow and all 40 finger names
    are correctly sided. Nothing in this pipeline reads those two entries.)
    """
    report = {}
    for tid in track_ids:
        n_hand = n_foot = n_seen = 0
        for i, frame in enumerate(per_frame):
            person = frame.get(tid) if isinstance(frame, dict) else None
            if person is None:
                continue
            n_seen += 1
            det = raw_detections[i] if i < len(raw_detections) else None
            kpts = body_box = None
            if det is not None:
                m = np.nonzero(np.asarray(det["track_ids"]) == tid)[0]
                if len(m):
                    kpts, body_box = det["keypoints"][m[0]], det["boxes"][m[0]]

            conf = np.zeros(2, dtype=np.float32)
            hand_boxes, foot_boxes = [], []
            if kpts is not None and body_box is not None:
                side = _box_side(body_box)
                chain = person.get("bone_length_confidence")
                for k, (ci, bkey, ji) in enumerate(
                    ((L_WRIST, "lhand_bbox", wrist_joint_idx[0]),
                     (R_WRIST, "rhand_bbox", wrist_joint_idx[1]))
                ):
                    if kpts[ci, 2] <= MIN_KEYPOINT_CONF:
                        continue  # the estimator's own box fell back to the body centre
                    box = np.asarray(person[bkey], dtype=np.float64) if bkey in person else None
                    if box is None:
                        cx, cy = kpts[ci, 0], kpts[ci, 1]
                        box = np.array([cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2])
                    hand_boxes.append(box)
                    cc = float(chain[ji]) if chain is not None and ji < len(chain) else 1.0
                    conf[k] = hand_pose_confidence(float(kpts[ci, 2]), float(box[2] - box[0]), cc)
                for ci in (L_ANKLE, R_ANKLE):
                    if kpts[ci, 2] <= MIN_KEYPOINT_CONF:
                        continue
                    cx, cy = float(kpts[ci, 0]), float(kpts[ci, 1])
                    foot_boxes.append(np.array([cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]))

            hand_rect = _rect(hand_boxes, frame_width, frame_height)
            foot_rect = _rect(foot_boxes, frame_width, frame_height)

            person["hand_crop_rect"] = hand_rect
            person["foot_crop_rect"] = foot_rect
            person["hand_confidence"] = conf
            n_hand += hand_rect is not None
            n_foot += foot_rect is not None
        if n_seen:
            report[tid] = {"n_frames": n_seen, "n_hand_rects": n_hand, "n_foot_rects": n_foot}
    return report
