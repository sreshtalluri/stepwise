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
    repair_clip_orientation,
    repair_orientation_detours,
    smooth_clip_result,
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


def test_bone_constraint_correction_reaches_the_suppression_stage():
    """INTEGRATION (docs/INTEGRATION.md): the `correction_m` seam.

    smoothing.py documents an optional `correction_m` input -- how far the
    upstream bone-length constraint had to move each joint -- and turns a
    large correction into `low_confidence`. skeleton_constraints.constrain_clip
    is the thing that does the moving. Neither branch could wire the two
    together (each was cut from w4-jobservice, before the other existed), so
    the seam was documented on both sides and connected on neither: the signal
    was silently dropped at integration.

    This checks the whole hop: constrain_clip records the displacement on the
    person dict -> smooth_clip_result reads it -> a joint the constraint had to
    yank stops being reported as plainly `observed`.
    """
    from skeleton_constraints import constrain_clip

    names, parents, offsets = _skeleton()
    F, J = 20, len(names)
    rng = np.random.default_rng(11)
    skel, _, _ = _build(rng.normal(scale=0.05, size=(F, J, 3)), offsets, parents)
    # constrain_clip's own convention (see its jc_to_ss): pred_joint_coords is
    # metres, skel_state translation is the same thing in cm with y/z negated.
    world = skel[..., :3] * np.array([1.0, -1.0, -1.0]) / 100.0

    per_frame = []
    for i in range(F):
        coords = world[i].copy()
        if i == 10:
            coords[-1] += 0.5  # one frame where the end joint is badly wrong
        per_frame.append({7: {
            "pred_joint_coords": coords.astype(np.float32),
            "skel_state": skel[i].astype(np.float32),
        }})

    constrain_clip(per_frame, [7], parents=parents, coincident=())
    assert "bone_length_correction_m" in per_frame[10][7], \
        "constrain_clip must record how far it moved each joint"

    dets = [{"track_ids": np.array([], dtype=int),
             "keypoints": np.zeros((0, 17, 3))} for _ in range(F)]
    out = smooth_clip_result(
        {"per_frame": per_frame, "raw_detections": dets,
         "sample_times_s": np.arange(F) * DT, "confident_track_ids": [7],
         "frame_width": 0, "frame_height": 0},
        hierarchy={"joints": [{"name": n, "parent_index": int(p)}
                              for n, p in zip(names, parents)]},
    )
    assert out[7]["visibility"][10, -1] != OBSERVED, \
        "a joint the bone constraint had to yank must not come back plain `observed`"


def _turning_body(F, yaw_deg_per_frame, bend_rad=0.4):
    """A whole body yawing steadily about +y, the right arm lifting slowly."""
    names, parents, offsets = _skeleton()
    rv = np.zeros((F, len(names), 3))
    rv[:, 0, 1] = np.radians(yaw_deg_per_frame) * np.arange(F)
    rv[:, names.index("r_uparm"), 2] = np.linspace(0.0, bend_rad, F)
    skel, _, _ = _build(rv, offsets, parents)
    return names, parents, skel


def _flip(skel_row, names, parents):
    """What the estimator emits on a hood frame: the body turned 180 deg about
    the vertical, with left and right limbs traded (a mirror, not a turn)."""
    off, lq, ls = decompose(skel_row[None], parents)
    other = {n: {"l": "r", "r": "l"}.get(n[0], n[0]) + n[1:] for n in names}
    swap = [names.index(other[n]) if other[n] in names else i for i, n in enumerate(names)]
    lq = lq[:, swap] * np.array([1, -1, -1, 1])  # mirror x: (x, y, z, w) -> (x, -y, -z, w)
    lq[:, 0] = (Rotation.from_euler("y", 180, degrees=True) * Rotation.from_quat(lq[0, 0])).as_quat()
    return recompose(off, lq, ls, parents)[0]


def test_one_and_two_frame_flips_are_repaired_and_the_rest_is_untouched():
    F = 40
    names, parents, skel = _turning_body(F, 2.0)
    flipped = skel.copy()
    flipped[10] = _flip(skel[10], names, parents)
    flipped[25] = _flip(skel[25], names, parents)
    flipped[26] = _flip(skel[26], names, parents)
    fixed, bad = repair_orientation_detours(np.arange(F) * DT, flipped, np.ones(F, bool), parents, 0)
    assert np.flatnonzero(bad).tolist() == [10, 25, 26], np.flatnonzero(bad)
    assert np.array_equal(fixed[~bad], flipped[~bad]), "unflagged samples must be byte-identical"
    # Back on the true pose (the truth here is exactly the interpolation), to float32.
    assert np.abs(fixed[bad, :, :3] - skel[bad, :, :3]).max() < 0.05  # cm
    q = Rotation.from_quat(fixed[:, 0, 3:7])
    assert np.degrees((q[1:] * q[:-1].inv()).magnitude()).max() < 2.5


def test_real_turns_and_fast_spins_are_left_alone():
    t = np.arange(60) * DT
    for yaw in (12.0, 40.0, 70.0):  # a slow full turn, a quick one, a spin faster than 1 rev/s
        _, parents, skel = _turning_body(60, yaw)
        fixed, bad = repair_orientation_detours(t, skel, np.ones(60, bool), parents, 0)
        assert not bad.any(), (yaw, np.flatnonzero(bad))
        assert np.array_equal(fixed, skel.astype(np.float32))


def test_a_flip_next_to_a_gap_is_not_guessed_at():
    F = 20
    names, parents, skel = _turning_body(F, 2.0)
    skel[8] = _flip(skel[8], names, parents)
    observed = np.ones(F, bool)
    observed[7] = False  # no observed neighbour on one side: no evidence which side is right
    _, bad = repair_orientation_detours(np.arange(F) * DT, skel, observed, parents, 0)
    assert not bad.any()


def test_repair_clip_orientation_keeps_the_estimate_and_flags_it():
    F = 20
    names, parents, skel = _turning_body(F, 2.0)
    skel[5] = _flip(skel[5], names, parents)
    per_frame = [{3: {"skel_state": skel[i].astype(np.float32)}} for i in range(F)]
    report = repair_clip_orientation(
        {"per_frame": per_frame, "sample_times_s": np.arange(F) * DT, "confident_track_ids": [3]},
        hierarchy={"root_joint_index": 0,
                   "joints": [{"name": n, "parent_index": int(p)} for n, p in zip(names, parents)]},
    )
    assert report == {3: [5]}
    assert per_frame[5][3]["orientation_repaired"] is True
    assert np.array_equal(per_frame[5][3]["skel_state_raw"], skel[5].astype(np.float32))
    assert "orientation_repaired" not in per_frame[4][3]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all smoothing self-checks passed")
