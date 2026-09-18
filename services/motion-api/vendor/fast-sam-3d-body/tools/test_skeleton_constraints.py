# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for skeleton_constraints.py.

No GPU, torch, or model weights -- a synthetic three-bone skeleton with known
bone lengths, posed randomly, then corrupted with exactly the defect measured
on real data (per-frame bone-length noise). The tests assert that the true
lengths come back, that the pose does not change, and that the confidence
signal fires on the frames that needed a big correction and not on the ones
that did not.

Run: python tools/test_skeleton_constraints.py   (or pytest)
"""
import json
import math
from pathlib import Path

import numpy as np

from skeleton_constraints import (
    MHR_COINCIDENT,
    MHR_PARENTS,
    UNCERTAIN_RATIO,
    bone_lengths,
    constrain_clip,
    enforce_bone_lengths,
    target_bone_lengths,
)

# root -> shoulder -> elbow -> wrist, plus a coincident marker on the wrist.
TOY_PARENTS = (-1, 0, 1, 2, 3)
TOY_COINCIDENT = frozenset({0, 4})
TRUE_LENGTHS = np.array([np.nan, 0.20, 0.30, 0.25, 0.001])


def _toy_clip(n_frames=200, noise=0.20, seed=0):
    """A rigid limb in random poses, then each bone's length corrupted by a
    random factor -- the defect, with the ground truth known."""
    rng = np.random.default_rng(seed)
    clean = np.zeros((n_frames, len(TOY_PARENTS), 3))
    for j, p in enumerate(TOY_PARENTS):
        if p < 0:
            clean[:, j] = rng.normal(0, 1.0, (n_frames, 3))  # global position wanders
            continue
        d = rng.normal(0, 1, (n_frames, 3))
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        clean[:, j] = clean[:, p] + d * TRUE_LENGTHS[j]
    dirty = clean.copy()
    factors = np.exp(rng.normal(0, noise, (n_frames, len(TOY_PARENTS))))
    for j, p in enumerate(TOY_PARENTS):
        if p < 0:
            continue
        v = clean[:, j] - clean[:, p]
        dirty[:, j] = dirty[:, p] + v * factors[:, j, None]
    return clean, dirty, factors


def test_recovers_true_bone_lengths_from_noisy_observations():
    clean, dirty, _ = _toy_clip()
    before = bone_lengths(dirty, TOY_PARENTS)[:, 1]
    assert before.std() / before.mean() > 0.15, "the synthetic defect is not actually there"

    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    after = bone_lengths(fixed.joints, TOY_PARENTS)

    for j in (1, 2, 3):
        assert np.nanstd(after[:, j]) < 1e-9, f"bone {j} still changes length"
        # The median estimator has to land on the truth, not just on something
        # constant -- 200 frames of 20% log-noise leaves a few percent of
        # sampling error, no more.
        assert abs(fixed.targets[j] - TRUE_LENGTHS[j]) / TRUE_LENGTHS[j] < 0.05


def test_correction_changes_length_only_never_direction():
    """The honesty property: this stage may not move a joint anywhere its
    observed bone direction did not already point."""
    _, dirty, _ = _toy_clip()
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    for j, p in enumerate(TOY_PARENTS):
        if p < 0:
            continue
        a = dirty[:, j] - dirty[:, p]
        b = fixed.joints[:, j] - fixed.joints[:, p]
        cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
        assert np.all(cos > 1 - 1e-9), f"bone {j} changed direction"


def test_root_position_is_untouched():
    """Global placement belongs to the grounding stage, not this one."""
    _, dirty, _ = _toy_clip()
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    assert np.allclose(fixed.joints[:, 0], dirty[:, 0])


def test_corrections_compose_down_the_chain():
    """A shoulder correction must carry the elbow and wrist with it, instead of
    each joint being re-fought against the uncorrected parent."""
    clean, dirty, _ = _toy_clip()
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    # Elbow-to-root distance is a two-bone sum; if the shoulder correction had
    # not propagated, the wrist would sit at the old (wrong) absolute position.
    moved = np.linalg.norm(fixed.joints[:, 3] - dirty[:, 3], axis=1)
    assert moved.mean() > 0.01, "distal joints did not move with their chain"


def test_coincident_marker_is_preserved_not_enforced():
    _, dirty, _ = _toy_clip()
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    assert not np.isfinite(fixed.targets[4]), "a declared marker was treated as a bone"
    offset_in = dirty[:, 4] - dirty[:, 3]
    offset_out = fixed.joints[:, 4] - fixed.joints[:, 3]
    assert np.allclose(offset_in, offset_out)


def test_confidence_tracks_the_size_of_the_correction():
    _, dirty, factors = _toy_clip()
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    # only the three bones between the root and the wrist -- factors[:, 4] is
    # the marker hanging off the wrist, not an ancestor of it.
    worst = np.abs(np.log(factors[:, 1:4])).max(axis=1)
    # Frames the constraint barely touched are trusted; badly-corrected frames
    # are not. Monotone, not just different.
    assert np.corrcoef(worst, np.nan_to_num(fixed.confidence[:, 3]))[0, 1] < -0.9
    calm = worst <= np.quantile(worst, 0.1)
    wild = worst >= np.quantile(worst, 0.9)
    assert fixed.confidence[calm, 3].mean() - fixed.confidence[wild, 3].mean() > 0.3
    # and the absolute scale is the documented one: a 2x correction is zero.
    assert fixed.confidence[worst > math.log(2.0), 3].max(initial=0.0) == 0.0


def test_a_joint_needing_a_3x_correction_is_flagged_uncertain():
    """The brief's explicit requirement: do not silently normalise away the
    evidence that something was wrong."""
    _, dirty, _ = _toy_clip(n_frames=50, noise=0.01)
    dirty[7, 2:] += (dirty[7, 2] - dirty[7, 1]) * 2.0  # elbow 3x too far out
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    assert fixed.uncertain[7, 2], "3x correction was not flagged"
    assert fixed.confidence[7, 2] == 0.0
    # and it propagates: the wrist hanging off that elbow is not trustworthy
    # either, even though its own bone was fine.
    assert fixed.uncertain[7, 3]
    assert not fixed.uncertain[6].any() and not fixed.uncertain[8].any()


def test_quiet_frames_are_not_flagged():
    _, dirty, _ = _toy_clip(n_frames=200, noise=0.02)
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    flagged = fixed.uncertain.any(axis=1).mean()
    assert flagged < 0.35, f"{flagged:.0%} of near-clean frames flagged uncertain"
    assert UNCERTAIN_RATIO > 1.0


def test_absent_frames_stay_absent():
    """Absent is not uncertain, and nothing gets filled in."""
    _, dirty, _ = _toy_clip(n_frames=30)
    dirty[5] = np.nan
    fixed = enforce_bone_lengths(dirty, TOY_PARENTS, coincident=TOY_COINCIDENT)
    assert np.all(np.isnan(fixed.joints[5]))
    assert np.all(np.isnan(fixed.confidence[5]))
    assert not fixed.uncertain[5].any()
    assert np.isfinite(fixed.joints[np.arange(30) != 5]).all()


def test_target_lengths_ignore_bones_seen_too_few_times():
    _, dirty, _ = _toy_clip(n_frames=4)
    targets = target_bone_lengths(dirty, TOY_PARENTS, min_observations=5,
                                  coincident=TOY_COINCIDENT)
    assert not np.isfinite(targets).any()


def test_parent_table_matches_the_hierarchy_json():
    """MHR_PARENTS is a copy; mhr_joint_hierarchy.json is the source of truth."""
    here = Path(__file__).resolve()
    path = here.parents[3] / "mhr_joint_hierarchy.json"  # services/motion-api/
    if not path.exists():  # running from the Modal image, where only vendor/ is mounted
        return
    joints = json.loads(path.read_text())["joints"]
    assert tuple(j["parent_index"] for j in joints) == MHR_PARENTS
    assert len(MHR_PARENTS) == 127
    # and the marker set is exactly "zero rest offset from the parent"
    rest = [float(np.linalg.norm(j["rest_translation"])) for j in joints]
    assert {i for i, r in enumerate(rest) if r < 1e-4} == set(MHR_COINCIDENT)
    assert min(r for i, r in enumerate(rest) if i not in MHR_COINCIDENT) > 5e-3


def test_constrain_clip_rewrites_both_joint_coords_and_skel_state():
    """skel_state is what the GLB exporter reads; correcting only
    pred_joint_coords would leave the exported animation unfixed."""
    _, dirty, _ = _toy_clip(n_frames=20)
    per_frame = []
    for f in range(20):
        coords = dirty[f].astype(np.float32)
        skel = np.zeros((len(TOY_PARENTS), 8), dtype=np.float32)
        skel[:, :3] = coords * np.array([1.0, -1.0, -1.0]) * 100.0
        skel[:, 6] = 1.0
        per_frame.append({7: {"pred_joint_coords": coords, "skel_state": skel}})
    per_frame.insert(3, {})  # a frame where nobody was detected

    report = constrain_clip(per_frame, [7], TOY_PARENTS, coincident=TOY_COINCIDENT)

    assert report[7]["n_frames"] == 20 and report[7]["n_bones"] == 3
    coords = np.stack([f[7]["pred_joint_coords"] for f in per_frame if f])
    skel = np.stack([f[7]["skel_state"] for f in per_frame if f])
    assert np.nanstd(bone_lengths(coords, TOY_PARENTS)[:, 1]) < 1e-6
    # The two representations must still agree, or the viewer and the contract
    # disagree about where the body is.
    assert np.abs(skel[:, :, :3] * np.array([1.0, -1.0, -1.0]) * 0.01 - coords).max() < 1e-5
    assert per_frame[0][7]["bone_length_confidence"].shape == (len(TOY_PARENTS),)
    assert per_frame[3] == {}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
