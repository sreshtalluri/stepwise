# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Anatomical bone-length constraint: one dancer's skeleton, made rigid.

The defect this fixes, measured on the real `solo-01.npz` in Modal Volume
`stepwise-results` (291 reconstructed frames, one dancer, track 4):

    bone (parent -> child)          mean     std    CV      min      max
    r_uparm  -> r_lowarm  (39->40) 0.2121  0.0521  24.6%  0.0933  0.2786
    r_lowarm -> r_wrist_t (40->41) 0.2143  0.0440  20.5%  0.1325  0.2815
    l_lowleg -> l_foot     (3->4)  0.3941  0.0175   4.4%  0.3515  0.4427

A real humerus does not change length. Every one of those standard deviations
is error. It survives export: the GLB's *node translation* channels carry the
same 24.4% CV, so it is what the viewer plays, and it is what makes a body
read as contorted.

Why it happens (measured, not assumed): SAM 3D Body re-estimates MHR shape and
scale parameters independently on every frame. Upper-arm length correlates at
|r| = 0.84 with individual `scale_params` dimensions whose per-frame standard
deviation is ~0.5. It is NOT foreshortening -- correlation between bone length
and how far out of the image plane the bone points is 0.10 for the upper arm
and -0.02 for the forearm, i.e. nothing. And it is high-frequency, not drift:
mean frame-to-frame |dL| is 40% of the whole clip's standard deviation.

Two consequences for the fix:

1. A per-clip constant target length is the right model (the true value does
   not drift, so there is nothing for a per-frame target to track).
2. The estimator does not need a foreshortening correction, so the median is
   unbiased here -- see `target_bone_lengths`.

Measured after, on the same solo-01 track (291 frames, 117 real bones):

    all 117 bones          CV mean 6.05% -> 0.0000%, max 24.57% -> 0.0000%
    exported GLB           upper-arm translation channel CV 24.4% -> 0.0%
                           (real run of modal_app.py::export_clip_gltf)
    2D reprojection vs the RTMO detector's own keypoints, which never passed
    through MHR and are therefore independent evidence from the image:
        elbows   18.9 / 18.5 px -> 17.8 / 16.5 px   (-5.6% / -11.0%)
        wrists   27.5 / 26.6 px -> 25.1 / 24.1 px   (-9.0% /  -9.3%)
        ankles   51.2 / 51.1 px -> 53.9 / 53.8 px   (+5.2% /  +5.3%)
        all 12   27.1 px        -> 27.1 px          (-0.1%)
    The joints whose bones were worst (arms) move measurably *closer* to the
    image after the fix; the legs, whose bones were already within 4% CV, give
    back half a pixel. The body does not collapse toward a rest pose: mean
    per-joint motion 0.1093 -> 0.1065 m/frame, wrist trajectory correlation
    before/after >= 0.98 on all three axes.

What this module does NOT do, on purpose:

* No temporal filtering of any kind. Bone length is corrected within a single
  frame using only that frame's directions. Temporal smoothing and the
  suppression/hysteresis chain are a separate stage (docs/PRD.md section 4).
* No floor, ground contact, or root trajectory change -- joint 0 keeps its
  observed world position exactly.
* No pose invention. See `enforce_bone_lengths` for why this operation cannot
  change any joint's rotation.

Pipeline position: raw per-frame estimates -> THIS -> temporal smoothing and
suppression -> glTF export.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple, Optional, Sequence

import numpy as np

# MHR's 127-joint parent table, -1 at the root. Duplicated from
# services/motion-api/mhr_joint_hierarchy.json (which api.py serves and
# modal_app.py::dump_joint_hierarchy generates) because only
# vendor/fast-sam-3d-body is mounted into the Modal cv_image -- copying 127
# ints beats adding a file mount and a runtime read to the GPU path.
# test_skeleton_constraints.py asserts this stays byte-identical to the JSON,
# so the JSON remains the single source of truth.
MHR_PARENTS: tuple[int, ...] = (
    -1, 0, 1, 2, 3, 4, 5, 6, 7, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 18,
    19, 20, 21, 22, 23, 19, 19, 19, 19, 18, 18, 18, 18, 18, 1, 34, 35, 36, 37, 38,
    39, 40, 41, 42, 43, 44, 45, 46, 42, 48, 49, 50, 42, 52, 53, 54, 42, 56, 57, 58,
    42, 60, 61, 62, 63, 40, 40, 40, 40, 39, 39, 39, 39, 39, 37, 74, 75, 76, 77, 78,
    79, 80, 81, 82, 78, 84, 85, 86, 78, 88, 89, 90, 78, 92, 93, 94, 78, 96, 97, 98,
    99, 76, 76, 76, 76, 75, 75, 75, 75, 75, 37, 110, 110, 110, 113, 114, 114, 114, 117, 118,
    119, 120, 113, 122, 113, 124, 113,
)

# Joints that sit exactly on top of their parent in MHR's rest skeleton: both
# wrists, the four *_twist0_proc joints, both talocrurals, c_neck_twist0_proc,
# and the root. Not bones -- markers. Their rest offsets are 0 (or 1e-6) while
# the shortest real bone, c_tongue0, is 9.0mm, so the classification is a clean
# structural fact, not a threshold. "Enforcing" a length on them is dividing by
# noise: on solo-01 their observed offsets are ~1.6mm with a 67-84% CV. They are
# translated rigidly with their parent instead, which preserves them exactly.
# Derived from mhr_joint_hierarchy.json; test_skeleton_constraints.py checks it.
MHR_COINCIDENT = frozenset({0, 5, 13, 21, 29, 42, 69, 78, 105, 112})

# Confidence reaches 0 when the correction anywhere in a joint's chain was a
# factor of this. A bone the model got 2x wrong tells you nothing about where
# that joint was, whatever we do to its length afterwards.
CONFIDENCE_ZERO_RATIO = 2.0

# A joint is flagged uncertain when some bone between it and the root had to be
# corrected by more than this factor. Measured flag rates on real clips, as a
# share of (frame, joint) pairs over the 70 non-hand, non-face joints:
#
#   threshold   solo-01 t4   solo-07 t1   solo-07 t3
#      1.10x       50.1%        49.2%         5.1%
#      1.25x       16.4%        10.8%         0.0%   <- shipped
#      1.50x        4.6%         3.8%         0.0%
#      2.00x        0.6%         0.3%         0.0%
#
# 1.25x is the honest reading of a bone whose own CV is 20-25%: roughly one
# joint-frame in six on the bad clips, none at all on the clean track. Where
# exactly `uncertain` should start is a product/honesty decision that belongs
# with whoever owns the suppression stage and docs/DESIGN.md section 4 -- it is
# NOT settled in docs/OPEN-DECISIONS.md. Treat this as a default, and prefer
# the continuous `confidence` array, which needs no threshold at all.
UNCERTAIN_RATIO = 1.25


class SkeletonConstraint(NamedTuple):
    """Everything the correction produced, including the evidence it used.

    joints:      (F, J, 3) corrected positions, same frame/units as the input.
    targets:     (J,) per-dancer target bone length, NaN at the root and at
                 coincident joints.
    length_ratio:(F, J) observed length / target length before correction.
                 1.0 is a perfect frame. NaN where there is no bone or no
                 observation. This is the raw evidence -- keep it.
    confidence:  (F, J) in [0, 1], NaN on frames where the dancer was absent.
                 1 - |log r| / log(CONFIDENCE_ZERO_RATIO), where |log r| is the
                 WORST correction anywhere between the root and this joint --
                 a wrist hanging off a shoulder the model got wrong is not
                 trustworthy just because its own forearm happened to measure
                 right.
    uncertain:   (F, J) bool, that same chain error past UNCERTAIN_RATIO.
                 False on absent frames -- absent is a different state from
                 uncertain (docs/DESIGN.md section 4).
    """

    joints: np.ndarray
    targets: np.ndarray
    length_ratio: np.ndarray
    confidence: np.ndarray
    uncertain: np.ndarray


def _topological_order(parents: Sequence[int]) -> list[int]:
    """Root-outward order, so a joint is always placed after its parent."""
    order: list[int] = []
    children: dict[int, list[int]] = {}
    roots = []
    for j, p in enumerate(parents):
        if p < 0:
            roots.append(j)
        else:
            children.setdefault(p, []).append(j)
    stack = list(reversed(roots))
    while stack:
        j = stack.pop()
        order.append(j)
        stack.extend(reversed(children.get(j, [])))
    if len(order) != len(parents):
        raise ValueError("joint hierarchy is not a forest (cycle or bad parent index)")
    return order


def bone_lengths(joints: np.ndarray, parents: Sequence[int] = MHR_PARENTS) -> np.ndarray:
    """(F, J, 3) -> (F, J) distance from each joint to its parent. NaN at roots."""
    joints = np.asarray(joints, dtype=np.float64)
    par = np.asarray(parents, dtype=np.int64)
    out = np.full(joints.shape[:2], np.nan)
    has_parent = par >= 0
    idx = np.nonzero(has_parent)[0]
    out[:, idx] = np.linalg.norm(joints[:, idx] - joints[:, par[idx]], axis=-1)
    return out


def target_bone_lengths(
    joints: np.ndarray,
    parents: Sequence[int] = MHR_PARENTS,
    min_observations: int = 5,
    coincident: Iterable[int] = MHR_COINCIDENT,
) -> np.ndarray:
    """One target length per bone for this dancer, from this dancer's own clip.

    Median, not mean. Three reasons, all measured on solo-01:

    * The observed distribution is skewed toward *short* (upper-arm skew
      -0.72), because the failure mode is a limb collapsing in depth, not
      stretching. The mean is dragged 4% below the median by that tail
      (0.2121 vs 0.2203 m); the median has a 50% breakdown point and is not.
    * A 20%-trimmed mean lands within 1% of the median on every bone, so the
      extra parameter buys nothing.
    * The bias the median *would* be vulnerable to -- systematic
      foreshortening, which would shorten most frames rather than a tail of
      them -- is measurably absent here (see module docstring).

    Body proportions are constant for a person, so this is one number per bone
    for the whole clip. Bones with fewer than `min_observations` finite frames,
    and the `coincident` markers, get NaN (not a guess) -- `enforce_bone_lengths`
    translates those rigidly instead of enforcing anything.
    """
    lengths = bone_lengths(joints, parents)
    coincident = set(coincident)
    targets = np.full(lengths.shape[1], np.nan)
    for j in range(lengths.shape[1]):
        if j in coincident:
            continue
        seen = lengths[np.isfinite(lengths[:, j]), j]
        if len(seen) < min_observations:
            continue  # never saw this bone enough to have an opinion
        targets[j] = float(np.median(seen))
    return targets


def enforce_bone_lengths(
    joints: np.ndarray,
    parents: Sequence[int] = MHR_PARENTS,
    targets: Optional[np.ndarray] = None,
    coincident: Iterable[int] = MHR_COINCIDENT,
) -> SkeletonConstraint:
    """Give every bone its target length, keeping every bone's direction.

    Walks the hierarchy root-outward and re-places each joint at

        corrected[child] = corrected[parent] + unit(observed_child - observed_parent) * target

    so a correction made at the shoulder carries the whole arm with it instead
    of being re-fought at the elbow. Joint 0 keeps its observed position, so
    the body's global placement is untouched (that is the grounding stage's
    business, not this one's).

    World positions, not local rotations, and that is not a shortcut. Because
    every bone's *direction* in world space is preserved exactly, every joint's
    world rotation is preserved, and therefore so is every local rotation
    relative to its parent. The operation is exactly "edit the skeleton's rest
    offsets, keep the entire pose" -- the only edit that cannot invent motion.
    Direction is also the half the monocular model is actually good at: the 2D
    projection pins it down, while depth ambiguity is precisely what corrupts
    length.

    Frames with no observation (all-NaN) pass through as NaN -- absent stays
    absent, nothing is filled in.
    """
    joints = np.asarray(joints, dtype=np.float64)
    if joints.ndim != 3 or joints.shape[2] != 3:
        raise ValueError(f"expected (F, J, 3) joint positions, got {joints.shape}")
    par = np.asarray(parents, dtype=np.int64)
    if len(par) != joints.shape[1]:
        raise ValueError(f"{len(par)} parents for {joints.shape[1]} joints")

    if targets is None:
        targets = target_bone_lengths(joints, par, coincident=coincident)
    targets = np.asarray(targets, dtype=np.float64)

    n_frames, n_joints = joints.shape[:2]
    out = joints.copy()
    ratio = np.full((n_frames, n_joints), np.nan)
    # Worst |log(ratio)| seen anywhere between the root and this joint.
    chain_err = np.zeros((n_frames, n_joints))

    for j in _topological_order(par):
        p = par[j]
        if p < 0:
            continue
        v = joints[:, j] - joints[:, p]
        observed = np.linalg.norm(v, axis=-1)
        target = targets[j]
        if not np.isfinite(target):
            # Coincident marker or a bone we never saw enough of: translate it
            # rigidly with its corrected parent. Preserves the offset exactly,
            # claims nothing.
            out[:, j] = out[:, p] + v
            chain_err[:, j] = chain_err[:, p]
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            r = observed / target
        ratio[:, j] = r
        # A bone estimated at ~zero length has no direction to preserve. Do not
        # invent one (that is a temporal question) -- leave it collapsed and let
        # the confidence signal below drive it to 0 so downstream suppresses it.
        scale = np.where(observed > 1e-9, target / np.maximum(observed, 1e-9), 0.0)
        out[:, j] = out[:, p] + v * scale[:, None]
        with np.errstate(divide="ignore", invalid="ignore"):
            own = np.abs(np.log(np.where(r > 0, r, np.nan)))
        own = np.where(np.isfinite(own), own, np.inf)  # collapsed bone: maximal error
        chain_err[:, j] = np.maximum(chain_err[:, p], own)

    absent = ~np.isfinite(joints).all(axis=2)
    confidence = np.clip(1.0 - chain_err / np.log(CONFIDENCE_ZERO_RATIO), 0.0, 1.0)
    uncertain = chain_err > np.log(UNCERTAIN_RATIO)
    confidence[absent] = np.nan
    uncertain[absent] = False
    return SkeletonConstraint(out, targets, ratio, confidence, uncertain)


def constrain_clip(
    per_frame: Sequence[dict],
    track_ids: Sequence[int],
    parents: Sequence[int] = MHR_PARENTS,
    coincident: Iterable[int] = MHR_COINCIDENT,
) -> dict:
    """Apply the constraint in place to one clip's `process_clip` output.

    `per_frame[i]` is `{track_id: person_dict}` (empty dict = nobody seen).
    For every track, rewrites `pred_joint_coords` and the translation block of
    `skel_state`, and adds two new per-person arrays:

        bone_length_ratio       (J,) observed/target before correction
        bone_length_confidence  (J,) in [0, 1], whole-chain

    `skel_state` is the array `Character.save_gltf_from_skel_states` exports
    from, and its translation block is `pred_joint_coords` in centimetres with
    y and z negated (verified on solo-01: max abs difference 0 after the flip).
    Correcting only one of the two would leave the exported GLB unfixed --
    measured on the real solo-01 GLB, the node *translation* channels carry the
    full 24.4% CV, so this is the channel that reaches the viewer.

    Returns per-track diagnostics for logging. The per-joint confidence is the
    signal the suppression stage consumes; it is deliberately not collapsed to
    a single number here.
    """
    jc_to_ss = np.array([1.0, -1.0, -1.0]) * 100.0
    report = {}
    for tid in track_ids:
        present = [i for i, f in enumerate(per_frame) if tid in f]
        if not present:
            continue
        joints = np.stack([per_frame[i][tid]["pred_joint_coords"] for i in present])
        fixed = enforce_bone_lengths(joints, parents, coincident=coincident)
        # How far this stage had to move each joint, in metres (pred_joint_coords
        # is metres -- see jc_to_ss above, which scales by 100 to reach skel_state's
        # centimetres). smoothing.smooth_track takes this as `correction_m` and
        # turns an over-large correction into a `low_confidence` flag. Recorded
        # here because `pred_joint_coords` is overwritten in place below, so this
        # is the only moment the before/after difference exists.
        correction_m = np.linalg.norm(fixed.joints - joints, axis=-1)
        for k, i in enumerate(present):
            person = per_frame[i][tid]
            coords = fixed.joints[k].astype(np.float32)
            person["pred_joint_coords"] = coords
            person["bone_length_correction_m"] = correction_m[k].astype(np.float32)
            if "skel_state" in person:
                skel = np.array(person["skel_state"], dtype=np.float32)
                skel[:, :3] = (coords * jc_to_ss).astype(np.float32)
                person["skel_state"] = skel
            person["bone_length_ratio"] = fixed.length_ratio[k].astype(np.float32)
            person["bone_length_confidence"] = fixed.confidence[k].astype(np.float32)
        real = np.isfinite(fixed.targets)
        ratio = fixed.length_ratio[:, real]
        ratio = ratio[np.isfinite(ratio) & (ratio > 0)]
        worst = float(np.exp(np.abs(np.log(ratio)).max())) if ratio.size else float("nan")
        report[tid] = {
            "n_frames": len(present),
            "n_bones": int(real.sum()),
            "n_frames_with_uncertain_joint": int(fixed.uncertain.any(axis=1).sum()),
            "worst_correction_factor": worst,
            "mean_confidence": float(np.nanmean(fixed.confidence)),
        }
    return report
