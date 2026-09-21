# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for smoothing.py (W9). No GPU, no clip, no fixtures.

    python tools/test_smoothing.py      (or: pytest tools/test_smoothing.py)

The cases that matter, and would each let a real defect through if removed:

  * FK round trip -- everything else happens in parent-local space.
  * A quaternion whose sign flips (q and -q are the same rotation) must not
    move the body. This is the failure the "never filter quaternion
    components as scalars" rule exists to prevent.
  * A physically impossible jump must come back marked `uncertain`, not
    quietly smoothed into a confident-looking pose (docs/DESIGN.md sec 7h).
  * A real, sharp accent must survive un-flagged and un-smeared -- the
    opposite failure, and the one that makes a choreography tool useless.
  * A gap must not be filtered across, and must not be presented as observed.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from smoothing import (
    ABSENT,
    ANCHORS,
    LOW_CONFIDENCE,
    OBSERVED,
    OUT_OF_FRAME,
    UNCERTAIN,
    decompose,
    detector_joint_signals,
    recompose,
    smooth_track,
)

FPS = 15.0
DT = 1.0 / FPS


def _skeleton():
    """A toy skeleton with every anchor name plus one finger, chained so the
    end joint has a real lever arm. names, parents, offsets (metres)."""
    names = ["body_world", "c_spine0", "c_neck", "c_head", "l_clavicle", "l_uparm",
             "l_lowarm", "l_wrist", "l_index1", "r_clavicle", "r_uparm", "r_lowarm",
             "r_wrist", "l_upleg", "l_lowleg", "l_foot", "r_upleg", "r_lowleg", "r_foot"]
    assert set(ANCHORS) <= set(names), "toy skeleton must cover every detector anchor"
    parents = [-1, 0, 1, 2, 1, 4, 5, 6, 7, 1, 9, 10, 11, 0, 13, 14, 0, 16, 17]
    offsets = np.zeros((len(names), 3))
    offsets[:, 1] = 0.25  # every bone 25 cm along +y
    offsets[0] = 0.0
    return names, np.array(parents), offsets


def _build(local_rotvecs, offsets, parents):
    """(F, J, 3) rotation vectors -> (F, J, 8) world skel_states."""
    F, J = local_rotvecs.shape[0], local_rotvecs.shape[1]
    lq = np.stack([Rotation.from_rotvec(local_rotvecs[f]).as_quat() for f in range(F)])
    off = np.tile(offsets, (F, 1, 1))
    return recompose(off, lq, np.ones((F, J)), parents), off, lq


def _world(skel):
    return skel[..., :3] / 100.0


def test_fk_round_trip_is_exact():
    names, parents, offsets = _skeleton()
    rng = np.random.default_rng(0)
    rot = rng.normal(scale=0.4, size=(5, len(names), 3))
    skel, off, lq = _build(rot, offsets, parents)
    off2, lq2, ls2 = decompose(skel, parents)
    # 1e-6 m, not 0: recompose returns float32 to match the estimator's own
    # skel_state dtype, and that is the precision floor of the whole chain.
    assert np.abs(off2 - off).max() < 1e-6, "offsets must survive the round trip"
    assert np.minimum(np.abs(lq2 - lq), np.abs(lq2 + lq)).max() < 1e-6
    again = recompose(off2, lq2, ls2, parents)
    assert np.abs(again - skel).max() < 1e-3  # cm


def test_quaternion_sign_flip_does_not_move_the_body():
    """q and -q are the same rotation. Filtering the four components as
    scalars would read the flip as a 180-degree jump; filtering the
    tangent-space angle cannot see it at all."""
    names, parents, offsets = _skeleton()
    F, J = 40, len(names)
    rot = np.zeros((F, J, 3))
    rot[:, 5, 2] = np.linspace(0.0, 2.5, F)  # l_uparm sweeps 143 degrees
    skel, _, _ = _build(rot, offsets, parents)
    times = np.arange(F) * DT
    obs = np.ones(F, dtype=bool)

    flipped = skel.copy()
    flipped[10:25, :, 3:7] *= -1.0  # same rotations, opposite hemisphere

    a = smooth_track(times, skel, obs, parents)
    b = smooth_track(times, flipped, obs, parents)
    moved = np.abs(_world(a.skel_states) - _world(b.skel_states)).max()
    assert moved < 1e-6, f"hemisphere flip moved the body by {moved:.4f} m"
    assert (b.visibility == OBSERVED).all(), "a sign flip is not a loss of confidence"


def test_implausible_jump_is_marked_uncertain_not_smoothed_away():
    """The W9 defect, reproduced: one joint teleports and comes back. The
    contract requires the sample to be flagged, not silently fixed."""
    names, parents, offsets = _skeleton()
    F, J = 30, len(names)
    hand = names.index("l_index1")
    rot = np.zeros((F, J, 3))
    rot[:, 5, 2] = np.linspace(0.0, 0.6, F)  # a slow, plausible arm sweep
    skel, _, _ = _build(rot, offsets, parents)
    clean_pos = _world(skel).copy()

    rot_bad = rot.copy()
    rot_bad[15, 5, 2] += 1.2  # one frame, ~0.7 m at the hand, then back
    bad, _, _ = _build(rot_bad, offsets, parents)
    jump = np.linalg.norm(_world(bad)[15, hand] - _world(bad)[14, hand])
    assert jump > 0.5, f"test setup should produce a big jump, got {jump:.3f} m"

    res = smooth_track(np.arange(F) * DT, bad, np.ones(F, dtype=bool), parents)

    assert res.visibility[15, hand] == UNCERTAIN, "an impossible jump must be flagged"
    assert res.suppression[15, hand] == LOW_CONFIDENCE
    assert res.prov_observed[15, hand], "the estimator did produce this sample"
    # ... and the pose must not have followed the jump.
    followed = np.linalg.norm(_world(res.skel_states)[15, hand] - _world(bad)[15, hand])
    kept = np.linalg.norm(_world(res.skel_states)[15, hand] - clean_pos[15, hand])
    assert kept < followed, "the filter followed the implausible jump"


def test_real_accent_survives():
    """A sharp but physical hit: the arm is still, then snaps. It must not be
    flagged, and the sharpness must survive -- smearing this is the product
    failure, not just a numerical one."""
    names, parents, offsets = _skeleton()
    F, J = 40, len(names)
    rot = np.zeros((F, J, 3))
    ramp = np.zeros(F)
    ramp[20:] = np.arange(F - 20) * 0.4  # 6 rad/s from a standstill: a real accent
    rot[:, 5, 2] = ramp
    skel, _, _ = _build(rot, offsets, parents)
    res = smooth_track(np.arange(F) * DT, skel, np.ones(F, dtype=bool), parents)

    hand = names.index("l_index1")
    raw_speed = np.linalg.norm(np.diff(_world(skel)[:, hand], axis=0), axis=-1)
    new_speed = np.linalg.norm(np.diff(_world(res.skel_states)[:, hand], axis=0), axis=-1)
    assert res.visibility[20:, hand].max() == OBSERVED, "a real accent must not be flagged"
    assert new_speed.max() > 0.8 * raw_speed.max(), (
        f"accent flattened: peak {new_speed.max():.4f} vs {raw_speed.max():.4f} m/frame")
    # And it must land on the same frame -- lag is as bad as flattening. The
    # onset, not the argmax: once the arm is up to speed the curve is flat, so
    # the peak's index says nothing.
    onset_raw = int(np.argmax(raw_speed > 0.5 * raw_speed.max()))
    onset_new = int(np.argmax(new_speed > 0.5 * raw_speed.max()))
    assert abs(onset_new - onset_raw) <= 1, f"accent arrived late: {onset_new} vs {onset_raw}"
    assert new_speed[onset_raw] > 0.8 * raw_speed[onset_raw], "the hit itself got smeared"


def test_gap_is_not_filtered_across():
    names, parents, offsets = _skeleton()
    F, J = 40, len(names)
    rot = np.zeros((F, J, 3))
    rot[:, 5, 2] = np.linspace(0.0, 1.2, F)
    skel, _, _ = _build(rot, offsets, parents)
    obs = np.ones(F, dtype=bool)
    obs[15:25] = False  # a 0.67 s hole, far longer than the reset duration

    res = smooth_track(np.arange(F) * DT, skel, obs, parents)

    assert (res.visibility[15:25] != OBSERVED).all(), "a gap is not an observation"
    assert (~res.prov_observed[15:25]).all()
    assert res.prov_interpolated[15:25].all()
    # Re-entry restarts the block at the measurement instead of dragging the
    # pre-gap state across the hole.
    err = np.abs(_world(res.skel_states)[25] - _world(skel)[25]).max()
    assert err < 1e-3, f"re-entry did not restart the filter ({err:.4f} m off)"


def test_detector_signals_suppress_whole_regions():
    names, parents, offsets = _skeleton()
    F, J = 12, len(names)
    kps = np.full((F, 17, 3), 0.99)
    kps[..., 0] = 100.0  # inside a 640x480 frame
    kps[..., 1] = 200.0
    kps[4:8, 9, 2] = 0.05  # l_wrist: occluded for four frames
    kps[6, 15, 0] = -20.0  # l_ankle leaves the frame for one

    conf, oof = detector_joint_signals(kps, 640, 480, names, parents)
    assert np.isnan(conf).sum() == 0
    assert conf[5, names.index("l_index1")] < 0.1, "a finger answers to its wrist"
    assert oof[6, names.index("l_foot")], "the foot's keypoint left the frame"

    rot = np.zeros((F, J, 3))
    skel, _, _ = _build(rot, offsets, parents)
    res = smooth_track(np.arange(F) * DT, skel, np.ones(F, dtype=bool), parents,
                       joint_conf=conf, joint_out_of_frame=oof)
    assert res.visibility[5, names.index("l_index1")] == UNCERTAIN
    assert res.suppression[5, names.index("l_index1")] == LOW_CONFIDENCE
    assert res.visibility[6, names.index("l_foot")] == ABSENT
    assert res.suppression[6, names.index("l_foot")] == OUT_OF_FRAME
    assert res.visibility[0, names.index("c_head")] == OBSERVED, "clean frames stay clean"


def test_hysteresis_holds_the_degraded_state_through_the_catch_up():
    """The frame after a held sample is the one that moves twice as far. It
    must still be flagged when it does."""
    names, parents, offsets = _skeleton()
    F, J = 20, len(names)
    kps = np.full((F, 17, 3), 0.99)
    kps[..., 0] = 100.0
    kps[..., 1] = 200.0
    kps[8, 9, 2] = 0.02  # one bad wrist frame
    conf, oof = detector_joint_signals(kps, 640, 480, names, parents)
    rot = np.zeros((F, J, 3))
    rot[:, 5, 2] = np.linspace(0, 1.0, F)
    skel, _, _ = _build(rot, offsets, parents)
    res = smooth_track(np.arange(F) * DT, skel, np.ones(F, dtype=bool), parents,
                       joint_conf=conf, joint_out_of_frame=oof)
    wrist = names.index("l_wrist")
    assert res.visibility[8, wrist] == UNCERTAIN, "degrade immediately"
    assert res.visibility[9, wrist] == UNCERTAIN, "and stay degraded through the catch-up"
    assert res.visibility[14, wrist] == OBSERVED, "but recover"


def test_bone_lengths_are_left_to_the_bone_constraints_module():
    """Smoothing must not quietly change bone lengths -- whatever the upstream
    per-frame constraint set has to survive this stage unchanged."""
    names, parents, offsets = _skeleton()
    F, J = 25, len(names)
    rng = np.random.default_rng(3)
    rot = rng.normal(scale=0.2, size=(F, J, 3))
    skel, off, _ = _build(rot, offsets, parents)
    res = smooth_track(np.arange(F) * DT, skel, np.ones(F, dtype=bool), parents)
    off_out, _, _ = decompose(res.skel_states, parents)
    lengths_in = np.linalg.norm(off[:, 1:], axis=-1)
    lengths_out = np.linalg.norm(off_out[:, 1:], axis=-1)
    assert np.abs(lengths_in - lengths_out).max() < 1e-4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all smoothing self-checks passed")
