"""Tests for world placement. Pure numpy, no GPU, no Modal, no fixtures.

The important test here is `test_under_crouched_reconstruction_does_not_slide`.
It builds the exact failure this module exists to prevent: a dancer who gets low
in ONE SPOT, and a reconstruction that under-crouches, so the only way to make
the too-tall body match the shrinking image is to push it away. Placement driven
by apparent size alone does exactly that, and a dancer who slides backwards every
time they bend their knees reads as broken immediately. The contact constraint is
what stops it, and this test fails if that constraint is ever weakened.

    python3 -m pytest services/motion-api/test_world_placement.py -q
"""
import numpy as np
import pytest

import world_placement as wp
from grounding import FOOT_JOINTS


FOCAL = 1000.0
WIDTH, HEIGHT = 640, 1024
JOINT_NAMES = ["body_world", "root"] + list(FOOT_JOINTS["left"]) + list(FOOT_JOINTS["right"])
ROOT = JOINT_NAMES.index("root")


def _body(crouch_m, lift=(0.0, 0.0)):
    """A crude upright body in the camera convention (Y down), root-relative.

    `crouch_m` lowers everything above the feet; `lift` raises one foot at a
    time so the scene has real steps -- without them every foot sample lands on
    the same two points and no plane is determined, which is a degenerate scene
    rather than a simple one.
    """
    joints = np.zeros((len(JOINT_NAMES), 3))
    feet_y = 0.95
    for k, side in enumerate(("left", "right")):
        x = -0.12 if side == "left" else 0.12
        for j, name in enumerate(FOOT_JOINTS[side]):
            joints[JOINT_NAMES.index(name)] = [x, feet_y - lift[k] - 0.02 * j, 0.03 * j]
    joints[ROOT] = [0.0, crouch_m, 0.0]

    keypoints = np.zeros((70, 3))
    # nose, eyes, ears, shoulders, elbows, hips, knees, ankles -- enough spread
    # in both image axes that the three translation unknowns are well posed.
    layout = {
        0: (0.0, -0.75), 1: (-0.04, -0.78), 2: (0.04, -0.78),
        3: (-0.08, -0.76), 4: (0.08, -0.76),
        5: (-0.18, -0.6), 6: (0.18, -0.6), 7: (-0.22, -0.35), 8: (0.22, -0.35),
        9: (-0.14, 0.0), 10: (0.14, 0.0), 11: (-0.12, 0.45), 12: (0.12, 0.45),
        13: (-0.12, 0.95), 14: (0.12, 0.95),
        62: (-0.24, -0.1), 41: (0.24, -0.1),
    }
    for idx, (x, y) in layout.items():
        # everything above the ankles sinks with the crouch; the ankles do not
        share = 0.0 if idx in (13, 14) else (0.95 - y) / 1.7
        lifted = lift[0] if idx == 13 else lift[1] if idx == 14 else 0.0
        keypoints[idx] = [x, y + crouch_m * share - lifted, 0.0]
    return joints, keypoints


# The clip: step, step, then hold still and crouch, then step again. The hold is
# the window under test; the steps exist so the foot samples span a floor.
HOLD = (45, 90)
N_FRAMES = 135


def _schedule(i):
    """(floor position, crouch depth, per-foot lift) at frame i.

    The walk curves on purpose. A dancer who crosses the floor in a dead
    straight line leaves foot samples on a LINE, and infinitely many planes
    contain a line -- that is a degenerate scene, not a simple one, and it would
    test the plane fit's luck rather than this module's placement.
    """
    if i < HOLD[0]:
        travel, phase = i / HOLD[0], i
    elif i < HOLD[1]:
        return _arc(1.0), np.sin(np.pi * (i - HOLD[0]) / (HOLD[1] - HOLD[0])), (0.0, 0.0)
    else:
        travel, phase = 1.0 + (i - HOLD[1]) / (N_FRAMES - HOLD[1]), i
    step = np.sin(2 * np.pi * phase / 18.0)
    return _arc(travel), 0.0, (0.12 * max(step, 0.0), 0.12 * max(-step, 0.0))


def _arc(travel):
    """Position on the floor: a quarter-circle-ish path, metres."""
    angle = 1.1 * travel
    return np.array([1.8 * np.sin(angle), 2.2 * (1.0 - np.cos(angle))])


def _clip(crouch_depth=0.40, reconstruction_fidelity=0.5, depth_m=4.0, walking=True):
    """A dancer who steps across the floor, then crouches in one spot.

    `reconstruction_fidelity` 1.0 is a perfect reconstruction; 0.5 means the
    reconstructed body only bends half as far as the real one did, which is the
    measured failure mode -- the leftover has to go somewhere, and placement
    driven by apparent size sends it into depth.
    """
    per_frame, raw = [], []
    for i in range(N_FRAMES):
        where, crouch, lift = _schedule(i)
        crouch *= crouch_depth
        if not walking:
            where, lift = _arc(1.0), (0.0, 0.0)
        t_true = np.array([where[0] - 1.6, -0.1, depth_m + where[1]])
        _, true_kp = _body(crouch, lift)
        rec_joints, rec_kp = _body(crouch * reconstruction_fidelity, lift)
        seen = true_kp + t_true
        uv = np.stack([FOCAL * seen[:, 0] / seen[:, 2] + WIDTH / 2,
                       FOCAL * seen[:, 1] / seen[:, 2] + HEIGHT / 2], axis=1)
        coco = np.zeros((1, 17, 3))
        coco[0, :, :2] = uv[wp.COCO_TO_MHR70]
        coco[0, :, 2] = 1.0
        per_frame.append({7: {
            "pred_joint_coords": rec_joints,
            "pred_keypoints_3d": rec_kp,
            "focal_length": np.float32(FOCAL),
        }})
        raw.append({"keypoints": coco, "track_ids": np.array([7])})
    return {
        "per_frame": per_frame,
        "raw_detections": raw,
        "confident_track_ids": np.array([7]),
        "sample_times_s": np.arange(N_FRAMES) / 15.0,
        "frame_width": WIDTH,
        "frame_height": HEIGHT,
    }, None


def _placed(npz, **kwargs):
    placement = wp.place_clip(npz, JOINT_NAMES, **kwargs)
    assert placement is not None
    roots = placement.root_positions[7]
    return placement, roots


def _placed_with_window(npz):
    """Place the clip, and report which frames the solve had contact evidence on.

    The window matters and is not a convenience. The claim this module makes is
    "a foot that is planted does not move", so the frames to hold it to are the
    frames where a foot is actually planted -- not the first and last few of the
    hold, where the dancer is still arriving at the pose and the feet are still
    moving. Outside contact there is nothing but apparent size, which is exactly
    the part that stays unreliable (see the module docstring).

    Captured through the public `contact_detector` seam rather than recomputed,
    so the test cannot drift away from what the solve actually used.
    """
    seen = []

    def recording(points, valid, times):
        weights = wp.detect_foot_contacts(points, valid, times)
        seen.append(weights)
        return weights

    placement = wp.place_clip(npz, JOINT_NAMES, contact_detector=recording)
    assert placement is not None
    hold = np.arange(*HOLD)
    supported = hold[seen[0][hold].max(axis=1) > 0.2]
    assert supported.size > 15, "the scene never produced a planted foot to test"
    return placement, placement.root_positions[7], slice(supported.min(), supported.max() + 1)


def _finite(roots, window):
    section = roots[window]
    return section[np.isfinite(section).all(axis=1)]


def test_under_crouched_reconstruction_does_not_slide():
    """The falsifiable one: crouching on planted feet must not move the dancer."""
    npz, _ = _clip()
    _, roots, window = _placed_with_window(npz)
    travel = np.ptp(_finite(roots, window), axis=0)
    # The pelvis genuinely drops, so vertical travel is expected and correct.
    # Horizontal travel on planted feet is the lie being tested for.
    horizontal = float(np.hypot(travel[0], travel[2]))
    assert horizontal < 0.10, f"dancer slid {horizontal:.2f} m while crouching in place"
    assert travel[1] > 0.05, "the crouch itself was smoothed away"


def test_contact_constraint_is_what_prevents_the_slide():
    """The same clip with contact evidence removed slides much further.

    Guards against the assertion above passing for some unrelated reason (the
    smoothing term, say) rather than because planted feet are holding depth.
    """
    npz, _ = _clip()
    placement, roots, window = _placed_with_window(npz)
    never = lambda points, valid, times: np.zeros(points.shape[:2])  # noqa: E731
    _, free = _placed(npz, contact_detector=never)
    slid = float(np.hypot(*np.ptp(_finite(free, window), axis=0)[[0, 2]]))
    held = float(np.hypot(*np.ptp(_finite(roots, window), axis=0)[[0, 2]]))
    assert placement.diagnostics["contact_links"] > 20
    assert slid > held * 3, f"contact made no difference ({held:.2f} m vs {slid:.2f} m)"


def test_real_travel_survives_the_contact_constraint():
    """The opposite failure: contact must not freeze a dancer who really moves."""
    npz, _ = _clip(crouch_depth=0.0)
    _, roots = _placed(npz)
    good = roots[np.isfinite(roots).all(axis=1)]
    assert float(np.ptp(good[:, 0])) > 1.2, "real lateral travel was smoothed away"


def test_camera_to_world_is_a_rigid_transform():
    npz, _ = _clip()
    placement, _ = _placed(npz)
    m = np.asarray(placement.camera_to_world).reshape(4, 4).T  # stored column-major
    rotation = m[:3, :3]
    assert np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-6)
    assert float(np.linalg.det(rotation)) == pytest.approx(1.0, abs=1e-6)
    assert m[3].tolist() == [0.0, 0.0, 0.0, 1.0]


def test_floor_is_at_y_zero_and_the_camera_is_above_it():
    npz, _ = _clip()
    placement, _ = _placed(npz)
    feet = placement.foot_tracks[0]
    heights = feet.points[feet.valid.all(axis=1) & feet.reconstructed][:, :, 1]
    assert abs(float(np.median(heights))) < 0.05
    assert placement.diagnostics["camera_height_above_floor_m"] > 0.0


def test_missing_frame_size_declines_rather_than_inventing_intrinsics():
    npz, _ = _clip()
    npz.pop("frame_width")
    assert wp.place_clip(npz, JOINT_NAMES) is None


def test_focal_is_labelled_a_prior_not_a_measurement():
    npz, _ = _clip()
    placement, _ = _placed(npz)
    assert "prior" in placement.diagnostics["focal_source"]
