# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""W9: temporal smoothing + honest suppression, across frames.

The defect, measured on the real `solo-01` reconstruction (291 frames,
127 joints, 15 fps, `stepwise-results` Volume):

    per-frame MEAN joint displacement   0.109 m  (p90 0.170, p99 0.214)
    per-frame MAX single-joint jump     0.271 m  (p90 0.420, max 0.583)

0.583 m in 1/15 s is 8.7 m/s at a single joint. No limb does that.

**But most of that number is the dance, not noise**, and that finding set
the design. A spectrum of the same world joint positions: 97% of the power
is below 3 Hz, 1% above 5 Hz, and extrapolating the flat 6-7.5 Hz level
across the band puts the white-noise share at ~0.1%. Human voluntary limb
motion is band-limited around 5 Hz, so at a 15 fps sample there is very
little high-frequency noise available to remove. A smoother aggressive
enough to move the headline jitter number therefore has to eat real
choreography -- an early version of this module did exactly that (mean
jitter -44%, and 41% of the sub-3 Hz motion gone with it). What is real in
the headline number is the *tail*: a thin set of samples whose implied
speed or acceleration no limb reaches. Those are marked, not smoothed away.

What this module does, and just as importantly what it refuses to do:

1.  Smooths *local* (parent-relative) joint rotations with independent
    constant-velocity Kalman filters (FilterPy), per docs/PRD.md section 4.
    Never filters quaternion components as scalars -- see `_rot_measurement`.
2.  Never turns a bad estimate into a confident-looking good one
    (docs/DESIGN.md section 7h). Every sample it did not take straight from a
    trusted measurement comes back flagged: `visibility` (observed /
    uncertain / absent) and `provenance` (observed / interpolated /
    suppressed) per packages/motion-contract/schema/motion-result.schema.json.
    A smoothed-over implausible jump is marked `uncertain`, never presented
    as recovered.
3.  Skips suppressed blocks entirely (docs/TASKS.md W9): a suppressed joint
    gets no filter update at all, and a gap longer than RESET_GAP_S restarts
    that joint's filter on re-entry instead of filtering across the hole.

Pure functions over per-frame arrays -- no torch, no CUDA, no I/O -- so it
drops into the pipeline at:

    raw per-frame estimates -> bone-length constraint -> THIS -> export

Module boundaries (three agents work on the same base):
  * Bone lengths / anatomical plausibility within a frame belong to the
    `bone-constraints` module. This one deliberately passes local bone
    offsets through untouched, so whatever lengths that module sets survive
    byte-for-byte. Measured cost of that choice on solo-01: freezing bone
    offsets entirely changes per-frame mean displacement by 0.109 -> 0.106 m,
    i.e. ~97% of the jitter is rotation, not length. Not worth owning.
    If that module emits a per-joint/per-frame correction magnitude, pass it
    as `correction_m` and large corrections become `low_confidence`.
  * Floor plane / foot contact belong to `grounding`.
  * Character/shape build belongs to `shape-params`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter
from scipy.spatial.transform import Rotation

CM_PER_M = 100.0

# --- motion-result.schema.json vocabulary, as integer codes -----------------
# Arrays, not strings, so this survives an npz round trip. Index into the
# *_NAMES tuples to get the exact contract spelling.
VISIBILITY_NAMES = ("observed", "uncertain", "absent")
OBSERVED, UNCERTAIN, ABSENT = 0, 1, 2

SUPPRESSION_NAMES = (None, "low_confidence", "out_of_frame")
NOT_SUPPRESSED, LOW_CONFIDENCE, OUT_OF_FRAME = 0, 1, 2

# --- physical constants, each with the reason it has that value ------------

# The implausible-motion gate, half one. A measured sample is rejected when
# the acceleration it implies is one no limb produces: the second difference
# of a joint's world position over three consecutive frames is a * dt^2.
#
# 150 m/s^2 is ~15 g. Sport-biomechanics peak *segment* accelerations for the
# fastest human actions (a thrown hand, a kicked foot) sit around 10-15 g;
# choreography is well below that. At 15 fps that allows 0.67 m of
# second-difference in one 67 ms frame -- so a real accent, which is a
# sustained change of velocity, passes, and a teleport-and-return does not.
# Measured on solo-01: it rejects 0.18% of joint-samples. Deliberately at the
# top of the human range rather than the middle: `uncertain` has to mean
# something, and over-marking is its own dishonesty.
A_MAX_MPS2 = 150.0

# Half two: a speed no joint of a dancing person reaches. The fastest hand
# speeds ever measured on a human are 9-11 m/s (an elite boxer's punch, a
# thrown ball's release); *averaged over a whole 67 ms sample*, 8 m/s at a
# joint is already past what choreography does. This is the test that catches
# the defect W9 was opened for -- the 0.583 m single-frame jump on solo-01 is
# 8.7 m/s -- in the case where the jump is smooth enough over three frames to
# slip under the acceleration test above.
V_MAX_MPS = 8.0

# Detector keypoint confidence below this is treated as "cannot see it"
# (occlusion, blur, or the dancer facing away). Measured on solo-01: RTMO's
# per-keypoint scores are strongly bimodal -- median 0.98-1.00 when the
# keypoint is visible, collapsing below 0.1 when it is not -- so anything in
# 0.2-0.5 gives the same answer. 0.3 sits in the middle of that dead zone.
KP_CONF_LOW = 0.3

# Hysteresis (docs/PRD.md section 4: "so limbs do not flicker between states
# frame to frame"). Asymmetric on purpose, and only in one direction:
# degradation is immediate, recovery takes EXIT consecutive clean frames. A
# symmetric "must fail twice to degrade" rule would have swallowed
# single-frame failures entirely -- measured on solo-01, that is exactly where
# the filter's worst artifact lives, because the frame *after* a held sample
# is the one that catches up and moves twice as far as it should. Holding the
# degraded state through the catch-up is both the anti-flicker rule and the
# honest one; the only cost is showing uncertainty a few frames too long.
HYSTERESIS_ENTER = 1
HYSTERESIS_EXIT = 3

# Reset duration. A block with nothing to look at for longer than this
# restarts cold at its next real measurement instead of re-acquiring through
# the filter. 0.2 s = 3 frames at 15 fps: long enough to ride out a one- or
# two-frame dropout without a visible snap, short enough that the pose on the
# far side of a real gap is the estimator's, not a blend with pre-gap data.
RESET_GAP_S = 0.2

# Noise-model floors. R is measured per joint per axis from the clip itself
# (see `estimate_noise`); these keep a degenerate joint -- e.g. the
# procedural `*_twist*_proc` joints, whose measured noise is exactly 0 -- from
# producing a divide-by-zero or a filter that can never move again.
SIGMA_MEAS_FLOOR_RAD = 1e-3  # 0.06 deg
SIGMA_ACCEL_FLOOR = 2.0  # rad/s^2
SIGMA_MEAS_TRANS_FLOOR_M = 1e-4
SIGMA_ACCEL_TRANS_FLOOR = 1.0  # m/s^2

# Slack added to the physical gate for measurement noise itself: 3 cm at the
# joint, ~3 sigma of the per-frame world-position noise measured on solo-01.
# Without it the gate would reject plausible motion that merely arrived noisy.
GATE_NOISE_MARGIN_M = 0.03


def load_joint_hierarchy(path: Optional[str] = None) -> dict:
    """The MHR skeleton (names + parent indices), as checked into the repo.

    `services/motion-api/mhr_joint_hierarchy.json` is a static file generated
    once by modal_app.py::dump_joint_hierarchy -- "fixed for the life of
    schema v1.0.0" per motion-result.schema.json. Looked up in the place the
    Modal cv_image mounts it, then in the repo, so the same code runs on the
    worker and on a laptop.
    """
    import json
    import os

    candidates = [path] if path else []
    candidates += [
        os.environ.get("STEPWISE_JOINT_HIERARCHY"),
        "/app/mhr_joint_hierarchy.json",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "mhr_joint_hierarchy.json"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            with open(candidate) as f:
                return json.load(f)
    raise FileNotFoundError(
        "mhr_joint_hierarchy.json not found; set STEPWISE_JOINT_HIERARCHY or mount it at /app/"
    )


@dataclass
class SmoothedTrack:
    """One dancer's smoothed motion plus the honesty flags for every sample.

    All arrays are (F, ...) with F == len(sample_times_s): a value exists for
    every sample time, because the exporter needs one
    (`Character.save_gltf_from_skel_states` takes a dense (F, J, 8) array).
    The flags are what stop a dense array from being read as a dense *claim*.
    """

    skel_states: np.ndarray  # (F, J, 8) float32, cm/quat/scale -- same layout as input
    visibility: np.ndarray  # (F, J) int8, index into VISIBILITY_NAMES
    suppression: np.ndarray  # (F, J) int8, index into SUPPRESSION_NAMES
    prov_observed: np.ndarray  # (F, J) bool -- estimator produced a value for this sample
    prov_interpolated: np.ndarray  # (F, J) bool -- value came from the filter, not this frame
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Forward kinematics: world skel_state <-> parent-local transforms
#
# A momentum skel_state row is [tx ty tz, qx qy qz qw, s] holding the *world*
# transform of that joint. Filtering world positions joint-by-joint would
# stretch bones (and silently undo the bone-constraints module's work), so
# everything below happens in parent-local space and is recomposed at the end.
# Verified against real data: decompose -> recompose round-trips solo-01 to
# 5.7e-14 cm in float64 (1e-4 cm once cast back to the estimator's float32),
# and dividing by the parent scale (rather than ignoring it)
# drops median bone-length variation from CV 0.015 to CV 0.005, which is how
# we know the parent-scale composition is the right reading of the format.
# ---------------------------------------------------------------------------


def decompose(skel_states: np.ndarray, parents: Sequence[int]):
    """(F, J, 8) world skel_states -> (offsets_m, local_q, local_scale)."""
    t = np.asarray(skel_states[..., 0:3], dtype=np.float64) / CM_PER_M
    q = np.asarray(skel_states[..., 3:7], dtype=np.float64)
    s = np.asarray(skel_states[..., 7], dtype=np.float64)
    # Unreconstructed frames arrive as all-zero rows, and a zero-norm
    # quaternion is the exact bug that made every exported GLB render as
    # nothing (see the `fix(export): NaN frame 0` commit). Substitute identity
    # here rather than propagating NaN: these rows are ignored downstream
    # because `frame_observed` is False for them, but they must not poison the
    # arithmetic on the way.
    norms = np.linalg.norm(q, axis=-1)
    bad = ~np.isfinite(norms) | (norms < 1e-6)
    if bad.any():
        q = q.copy()
        q[bad] = (0.0, 0.0, 0.0, 1.0)
        s = np.where(np.isfinite(s) & (np.abs(s) > 1e-9), s, 1.0)
        t = np.nan_to_num(t, nan=0.0, posinf=0.0, neginf=0.0)
    F, J = t.shape[0], t.shape[1]
    off = np.zeros((F, J, 3))
    lq = np.zeros((F, J, 4))
    ls = np.ones((F, J))
    for j in range(J):
        p = parents[j]
        if p < 0:
            off[:, j], lq[:, j], ls[:, j] = t[:, j], q[:, j], s[:, j]
            continue
        rp = Rotation.from_quat(q[:, p])
        off[:, j] = rp.inv().apply(t[:, j] - t[:, p]) / s[:, p][:, None]
        lq[:, j] = (rp.inv() * Rotation.from_quat(q[:, j])).as_quat()
        ls[:, j] = s[:, j] / s[:, p]
    return off, lq, ls


def recompose(off: np.ndarray, lq: np.ndarray, ls: np.ndarray, parents: Sequence[int]) -> np.ndarray:
    """Inverse of `decompose`. Returns (F, J, 8) float32 in the input's units."""
    F, J = off.shape[0], off.shape[1]
    t = np.zeros((F, J, 3))
    q = np.zeros((F, J, 4))
    s = np.ones((F, J))
    for j in range(J):
        p = parents[j]
        if p < 0:
            t[:, j], q[:, j], s[:, j] = off[:, j], lq[:, j], ls[:, j]
            continue
        rp = Rotation.from_quat(q[:, p])
        t[:, j] = t[:, p] + s[:, p][:, None] * rp.apply(off[:, j])
        q[:, j] = (rp * Rotation.from_quat(lq[:, j])).as_quat()
        s[:, j] = s[:, p] * ls[:, j]
    out = np.concatenate([t * CM_PER_M, q, s[..., None]], axis=-1)
    return out.astype(np.float32)


def _lever_arms(pos: np.ndarray, parents: Sequence[int]) -> np.ndarray:
    """(J,) metres: how far the furthest thing a joint carries sits from it.

    This is what turns an angle into a distance, so one physical acceleration
    limit can gate every joint: a radian at the shoulder throws the hand
    0.6 m, a radian at a fingertip throws nothing. Computed once from a
    representative pose of this clip -- a leaf joint gets 0 and is therefore
    never gated, which is right: rotating a leaf moves no joint at all.
    """
    J = pos.shape[0]
    lever = np.zeros(J)
    for j in range(J):
        # Walk down: every descendant's distance from j is a candidate.
        stack = [c for c in range(J) if parents[c] == j]
        while stack:
            c = stack.pop()
            lever[j] = max(lever[j], float(np.linalg.norm(pos[c] - pos[j])))
            stack.extend(k for k in range(J) if parents[k] == c)
    return lever


def _world_positions(off: np.ndarray, lq: np.ndarray, ls: np.ndarray, parents: Sequence[int]) -> np.ndarray:
    """Single-frame FK, metres. off/lq/ls are (J, 3)/(J, 4)/(J,)."""
    J = off.shape[0]
    t = np.zeros((J, 3))
    q = np.zeros((J, 4))
    s = np.ones(J)
    for j in range(J):
        p = parents[j]
        if p < 0:
            t[j], q[j], s[j] = off[j], lq[j], ls[j]
            continue
        rp = Rotation.from_quat(q[p])
        t[j] = t[p] + s[p] * rp.apply(off[j])
        q[j] = (rp * Rotation.from_quat(lq[j])).as_quat()
        s[j] = s[p] * ls[j]
    return t


# ---------------------------------------------------------------------------
# Rotations without ever treating quaternion components as scalars
# ---------------------------------------------------------------------------


def _rot_measurement(q_nom: np.ndarray, q_meas: np.ndarray) -> np.ndarray:
    """The scalar angles the Kalman filters actually see: (J, 3) radians.

    This is the whole "never filter quaternion components as ordinary
    scalars" requirement, in one function. Instead of feeding qx/qy/qz/qw to
    four filters (which does not produce a valid rotation -- the unit-norm
    constraint is not linear, and q and -q are the same rotation so a sign
    flip looks like a 180 deg jump to a scalar filter), we filter the
    *tangent-space error* of the measurement against the filter's current
    nominal rotation:

        z = log(q_nom^-1 * q_meas)   in so(3), three genuinely independent,
                                     already-unwrapped scalar angles

    Unwrapping is structural rather than a post-hoc fixup: the residual of
    one 67 ms frame is a small rotation, `as_rotvec` returns an angle in
    [0, pi], and it is invariant to the q/-q hemisphere flip. The filtered
    result is injected back multiplicatively (`_rot_inject`), so the output
    is always a unit quaternion by construction, never a renormalized
    approximation of one.
    """
    return (Rotation.from_quat(q_nom).inv() * Rotation.from_quat(q_meas)).as_rotvec()


def _rot_inject(q_nom: np.ndarray, dtheta: np.ndarray) -> np.ndarray:
    """q_nom * exp(dtheta) -- the multiplicative counterpart of the log above."""
    return (Rotation.from_quat(q_nom) * Rotation.from_rotvec(dtheta)).as_quat()


def _tangent_series(lq: np.ndarray) -> np.ndarray:
    """(F, J, 4) quaternions -> (F, J, 3) rotation vectors about each joint's
    own mean rotation. Only used for noise estimation, and only because the
    estimate has to be made on an *unwrapped scalar* series -- the same reason
    the filters themselves never see quaternion components."""
    F, J = lq.shape[0], lq.shape[1]
    theta = np.zeros((F, J, 3))
    for j in range(J):
        mean_rot = Rotation.from_quat(lq[:, j]).mean()
        theta[:, j] = (mean_rot.inv() * Rotation.from_quat(lq[:, j])).as_rotvec()
    return theta


def _mad(x: np.ndarray) -> np.ndarray:
    return 1.4826 * np.median(np.abs(x - np.median(x, axis=0, keepdims=True)), axis=0)


def estimate_noise(series: np.ndarray, dt: float, sigma_floor: float, accel_floor: float):
    """Measure this clip's own noise floor and real acceleration scale.

    `series` is (F, ..., C) of unwrapped scalars (radians for rotations,
    metres for translation). Returns (sigma, accel) shaped like series[0].

    The filter is tuned from the data rather than by taste, because the only
    honest way to decide how much smoothing is too much is to know how much
    of the signal is noise:

      * sigma -- measurement noise. For white noise of std s, the third
        difference of a series has variance 20 s^2, while a real limb's third
        derivative at 15 fps is comparatively tiny. A median-absolute-
        deviation estimate (not std) keeps real accents from inflating it.
      * accel -- the clip's real acceleration scale, recovered by removing
        the noise contribution from the second difference
        (var(d2) = 6 sigma^2 + accel^2 dt^4). This becomes the process noise,
        so the filter is exactly as willing to follow acceleration as this
        dancer actually produced. That is the accent-preservation knob: set
        it lower and sharp hits smear; the point of measuring it is not to
        set it lower.
    """
    if series.shape[0] < 5:
        return (np.full(series.shape[1:], sigma_floor * 10), np.full(series.shape[1:], accel_floor))
    d2 = np.diff(series, n=2, axis=0)
    d3 = np.diff(series, n=3, axis=0)
    sigma = np.maximum(_mad(d3) / np.sqrt(20.0), sigma_floor)
    accel = np.sqrt(np.maximum(_mad(d2) ** 2 - 6.0 * sigma**2, 0.0)) / dt**2
    return sigma, np.maximum(accel, accel_floor)


def _make_cv_filter(dt: float, sigma_meas: float, sigma_accel: float):
    """One independent constant-velocity filter over one unwrapped scalar.

    State [x, xdot]. Q is the standard discrete white-noise-acceleration
    model. Independence per scalar is not a simplification for its own sake:
    it is what lets a suppressed joint's update be skipped outright instead of
    doing measurement-row surgery on a coupled filter (docs/PRD.md section 4).
    """
    kf = KalmanFilter(dim_x=2, dim_z=1)
    kf.x = np.zeros((2, 1))
    kf.F = np.array([[1.0, dt], [0.0, 1.0]])
    kf.H = np.array([[1.0, 0.0]])
    kf.R = np.array([[sigma_meas**2]])
    kf.P = np.diag([sigma_meas**2, (sigma_accel * dt) ** 2])
    kf.Q = Q_discrete_white_noise(dim=2, dt=dt, var=sigma_accel**2)
    return kf


def _set_dt(kf, dt: float, sigma_accel: float) -> None:
    """Recompute F and Q from the actual dt (docs/PRD.md section 4)."""
    kf.F[0, 1] = dt
    kf.Q = Q_discrete_white_noise(dim=2, dt=dt, var=sigma_accel**2)


# ---------------------------------------------------------------------------
# Detector -> per-joint visibility evidence
# ---------------------------------------------------------------------------

# COCO-17 keypoint indices (RTMO, to_openpose=False).
COCO = {
    "nose": 0, "l_eye": 1, "r_eye": 2, "l_ear": 3, "r_ear": 4,
    "l_shoulder": 5, "r_shoulder": 6, "l_elbow": 7, "r_elbow": 8,
    "l_wrist": 9, "r_wrist": 10, "l_hip": 11, "r_hip": 12,
    "l_knee": 13, "r_knee": 14, "l_ankle": 15, "r_ankle": 16,
}

# Which MHR joint each detector keypoint speaks for. Everything below an
# anchor in the skeleton inherits that anchor -- "a suppressed wrist
# suppresses the whole hand" (docs/PRD.md section 4's conservative region
# mapping). Values are lists of COCO keypoints plus how to combine them:
# "min" where every listed keypoint must be visible for the region to count
# as seen (the torso needs both shoulders and both hips), "max" where any one
# of them is enough (the head is visible if the nose OR an ear is).
ANCHORS = {
    "body_world": (["l_shoulder", "r_shoulder", "l_hip", "r_hip"], "min"),
    "c_spine0": (["l_shoulder", "r_shoulder", "l_hip", "r_hip"], "min"),
    "c_neck": (["l_shoulder", "r_shoulder"], "min"),
    "c_head": (["nose", "l_eye", "r_eye", "l_ear", "r_ear"], "max"),
    "l_clavicle": (["l_shoulder"], "min"),
    "r_clavicle": (["r_shoulder"], "min"),
    "l_uparm": (["l_shoulder", "l_elbow"], "min"),
    "r_uparm": (["r_shoulder", "r_elbow"], "min"),
    "l_lowarm": (["l_elbow", "l_wrist"], "min"),
    "r_lowarm": (["r_elbow", "r_wrist"], "min"),
    "l_wrist": (["l_wrist"], "min"),
    "r_wrist": (["r_wrist"], "min"),
    "l_upleg": (["l_hip", "l_knee"], "min"),
    "r_upleg": (["r_hip", "r_knee"], "min"),
    "l_lowleg": (["l_knee", "l_ankle"], "min"),
    "r_lowleg": (["r_knee", "r_ankle"], "min"),
    "l_foot": (["l_ankle"], "min"),
    "r_foot": (["r_ankle"], "min"),
}


def joint_anchor_map(joint_names: Sequence[str], parents: Sequence[int]) -> np.ndarray:
    """(J,) index of the ANCHORS joint each joint inherits evidence from.

    Walks up the skeleton to the nearest anchored ancestor, so the 44 hand /
    finger joints answer to their wrist and the toe joints answer to their
    ankle. -1 means no detector keypoint speaks for this joint at all (the
    tongue, the teeth) -- those stay at whatever their ancestor says.
    """
    name_to_idx = {n: i for i, n in enumerate(joint_names)}
    anchor_of = np.full(len(joint_names), -1, dtype=np.int64)
    for j, name in enumerate(joint_names):
        if name in ANCHORS:
            anchor_of[j] = j
            continue
        p = parents[j]
        anchor_of[j] = anchor_of[p] if p >= 0 else -1
    # Sanity: every anchor name must exist in this skeleton.
    missing = [n for n in ANCHORS if n not in name_to_idx]
    if missing:
        raise ValueError(f"skeleton is missing anchor joints: {missing}")
    return anchor_of


def detector_joint_signals(
    keypoints: np.ndarray,
    frame_width: int,
    frame_height: int,
    joint_names: Sequence[str],
    parents: Sequence[int],
):
    """Turn per-frame COCO-17 detections into per-joint visibility evidence.

    `keypoints` is (F, 17, 3) [x, y, score] in frame pixels, with a row of
    NaN for any frame where this track was not detected at all.

    Returns (conf, out_of_frame), both (F, J): the detector's confidence for
    the region each joint belongs to, and whether that region's keypoint left
    the frame. NaN confidence means "no evidence either way" -- the caller
    decides what that means, because *this* function refuses to guess.
    """
    keypoints = np.asarray(keypoints, dtype=np.float64)
    F = keypoints.shape[0]
    J = len(joint_names)
    name_to_idx = {n: i for i, n in enumerate(joint_names)}
    anchor_of = joint_anchor_map(joint_names, parents)

    anchor_conf = np.full((F, J), np.nan)
    anchor_oof = np.zeros((F, J), dtype=bool)
    x, y, c = keypoints[..., 0], keypoints[..., 1], keypoints[..., 2]
    # A keypoint predicted outside the frame is the detector saying the joint
    # left the picture (docs/DESIGN.md section 7h case 3), not a bad guess
    # inside it. Margin of 0 px: the frame edge is the claim boundary.
    oof_kp = (x < 0) | (x > frame_width) | (y < 0) | (y > frame_height)

    seen = ~np.all(np.isnan(c), axis=1)  # frames where this track was detected
    for name, (kps, how) in ANCHORS.items():
        j = name_to_idx[name]
        cols = [COCO[k] for k in kps]
        vals = c[np.ix_(seen, cols)]
        agg = np.nanmax(vals, axis=1) if how == "max" else np.nanmin(vals, axis=1)
        anchor_conf[seen, j] = agg
        # Out of frame is always "any of them left" -- conservative.
        anchor_oof[seen, j] = np.any(oof_kp[np.ix_(seen, cols)], axis=1)

    conf = np.full((F, J), np.nan)
    oof = np.zeros((F, J), dtype=bool)
    for j in range(J):
        a = anchor_of[j]
        if a >= 0:
            conf[:, j] = anchor_conf[:, a]
            oof[:, j] = anchor_oof[:, a]
    return conf, oof


# ---------------------------------------------------------------------------
# Visibility bookkeeping
# ---------------------------------------------------------------------------


def _propagate_to_descendants(severity: np.ndarray, reason: np.ndarray, parents: Sequence[int]):
    """A suppressed joint suppresses everything below it (docs/PRD.md sec 4).

    MHR's joint list is topologically ordered (every parent index is smaller
    than its child's), so one forward pass is enough.
    """
    for j, p in enumerate(parents):
        if p < 0:
            continue
        worse = severity[:, p] > severity[:, j]
        severity[worse, j] = severity[worse, p]
        reason[worse, j] = reason[worse, p]
    return severity, reason


def _hysteresis(severity: np.ndarray, reason: np.ndarray, enter=HYSTERESIS_ENTER, exit_=HYSTERESIS_EXIT):
    """Debounce state transitions so limbs do not flicker (docs/PRD.md sec 4)."""
    F, J = severity.shape
    out_sev = np.zeros_like(severity)
    out_reason = np.zeros_like(reason)
    cur = severity[0].copy()
    cur_reason = reason[0].copy()
    run = np.zeros(J, dtype=np.int64)
    candidate = cur.copy()
    for f in range(F):
        same = severity[f] == candidate
        run = np.where(same, run + 1, 1)
        candidate = severity[f]
        need = np.where(candidate > cur, enter, exit_)
        switch = (candidate != cur) & (run >= need)
        cur = np.where(switch, candidate, cur)
        cur_reason = np.where(switch, reason[f], cur_reason)
        # A state with no suppression reason cannot carry one.
        cur_reason = np.where(cur == OBSERVED, NOT_SUPPRESSED, cur_reason)
        out_sev[f] = cur
        out_reason[f] = cur_reason
    return out_sev, out_reason


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


def smooth_track(
    sample_times_s: np.ndarray,
    skel_states: np.ndarray,
    frame_observed: np.ndarray,
    parents: Sequence[int],
    *,
    joint_conf: Optional[np.ndarray] = None,
    joint_out_of_frame: Optional[np.ndarray] = None,
    correction_m: Optional[np.ndarray] = None,
) -> SmoothedTrack:
    """Smooth one dancer's motion and say honestly what happened to it.

    Args:
      sample_times_s: (F,) normalized sample times, seconds.
      skel_states: (F, J, 8) raw world skel_states. Rows where
        `frame_observed` is False are ignored, not trusted.
      frame_observed: (F,) bool -- did the estimator reconstruct this dancer
        on this sample at all.
      parents: (J,) parent index per joint, -1 for the root.
      joint_conf: (F, J) detector confidence for each joint's region, NaN
        where there is no evidence. From `detector_joint_signals`.
      joint_out_of_frame: (F, J) bool -- the region's keypoint left the frame.
      correction_m: (F, J) optional, metres. How far the upstream bone-length
        constraint had to move this joint. Optional by design: this module
        does not depend on the `bone-constraints` branch landing. When it is
        present, a correction larger than a limb's own noise floor is exactly
        the "we had to invent this" signal, and becomes `low_confidence`.

    Returns a SmoothedTrack whose `skel_states` are dense (the exporter needs
    a pose per sample) and whose flags say which of those poses are claims.
    """
    sample_times_s = np.asarray(sample_times_s, dtype=np.float64)
    skel_states = np.asarray(skel_states, dtype=np.float64)
    frame_observed = np.asarray(frame_observed, dtype=bool)
    F, J = skel_states.shape[0], skel_states.shape[1]
    parents = np.asarray(parents, dtype=np.int64)

    vis = np.full((F, J), ABSENT, dtype=np.int8)
    sup = np.full((F, J), OUT_OF_FRAME, dtype=np.int8)
    prov_obs = np.zeros((F, J), dtype=bool)
    prov_interp = np.zeros((F, J), dtype=bool)

    obs_idx = np.flatnonzero(frame_observed)
    if obs_idx.size == 0:
        # Nothing was ever reconstructed. Say so; do not invent a body.
        return SmoothedTrack(
            skel_states=np.zeros((F, J, 8), dtype=np.float32),
            visibility=vis, suppression=sup,
            prov_observed=prov_obs, prov_interpolated=prov_interp,
            stats={"n_frames": int(F), "n_observed_frames": 0, "empty": True},
        )

    off, lq, ls = decompose(skel_states, parents)
    dt_nominal = float(np.median(np.diff(sample_times_s))) if F > 1 else 1.0 / 15.0
    root = int(np.flatnonzero(parents < 0)[0])
    sigma, accel = estimate_noise(
        _tangent_series(lq[obs_idx]), dt_nominal, SIGMA_MEAS_FLOOR_RAD, SIGMA_ACCEL_FLOOR
    )
    # The root joint's offset is the body's world translation, not a bone
    # vector, so it gets the one translation filter docs/PRD.md section 4 asks
    # for -- measured the same way, in metres and m/s^2.
    trans_sigma, trans_accel = estimate_noise(
        off[obs_idx, root], dt_nominal, SIGMA_MEAS_TRANS_FLOOR_M, SIGMA_ACCEL_TRANS_FLOOR
    )

    # --- raw per-joint suppression evidence, before hysteresis -------------
    raw_sev = np.zeros((F, J), dtype=np.int8)
    raw_reason = np.zeros((F, J), dtype=np.int8)
    if joint_out_of_frame is not None:
        m = np.asarray(joint_out_of_frame, dtype=bool)
        raw_sev[m] = ABSENT
        raw_reason[m] = OUT_OF_FRAME
    if joint_conf is not None:
        conf = np.asarray(joint_conf, dtype=np.float64)
        low = (conf < KP_CONF_LOW) & ~np.isnan(conf)
        bump = low & (raw_sev < UNCERTAIN)
        raw_sev[bump] = UNCERTAIN
        raw_reason[bump] = LOW_CONFIDENCE
    if correction_m is not None:
        # The bone-constraints module had to move this joint further than its
        # own measurement noise: the frame's estimate was not usable as-is.
        corr = np.asarray(correction_m, dtype=np.float64)
        big = corr > np.maximum(3.0 * np.nanmedian(corr), 0.02)
        bump = big & (raw_sev < UNCERTAIN)
        raw_sev[bump] = UNCERTAIN
        raw_reason[bump] = LOW_CONFIDENCE
    # A frame with no reconstruction at all: no evidence about *why*, so the
    # honest answer is "uncertain" unless the detector said out-of-frame
    # above. docs/DESIGN.md section 7h -- `absent` is a claim too (case 3),
    # and claiming a dancer left the frame when they were merely lost is the
    # same kind of lie as claiming to have seen them.
    missing = ~frame_observed
    bump = missing[:, None] & (raw_sev < UNCERTAIN)
    raw_sev[bump] = UNCERTAIN
    raw_reason[bump] = LOW_CONFIDENCE

    raw_sev, raw_reason = _propagate_to_descendants(raw_sev, raw_reason, parents)

    # --- the filters -------------------------------------------------------
    # One independent constant-velocity filter per unwrapped scalar: three per
    # joint for the tangent-space rotation error, plus three for the root's
    # world translation. 384 filters for the MHR skeleton, ~4 s for a 20 s
    # clip -- next to 78 s of GPU reconstruction, not worth vectorizing.
    rot_kf = [[_make_cv_filter(dt_nominal, sigma[j, a], accel[j, a]) for a in range(3)] for j in range(J)]
    trans_kf = [_make_cv_filter(dt_nominal, trans_sigma[a], trans_accel[a]) for a in range(3)]
    for a in range(3):
        trans_kf[a].x[0, 0] = off[obs_idx[0], root, a]

    first = int(obs_idx[0])
    mid = int(obs_idx[len(obs_idx) // 2])
    lever = _lever_arms(_world_positions(off[mid], lq[mid], ls[mid], parents), parents)
    q_nom = lq[first].copy()
    off_hold = off[first].copy()
    ls_hold = ls[first].copy()
    stale = np.zeros(J, dtype=np.int64)  # frames since this block last updated
    needs_reset = np.zeros(J, dtype=bool)
    max_hold_frames = max(1, int(round(RESET_GAP_S / dt_nominal)))

    out_off = off.copy()
    out_lq = lq.copy()
    out_ls = ls.copy()
    n_gated = 0
    n_implausible = 0
    n_skipped = 0
    last_update_t = np.full(J, sample_times_s[first] - dt_nominal)
    prev_meas_pos = None  # world positions at the previous two observed frames
    prev2_meas_pos = None
    prev_meas_f = None
    prev_lq = lq[first].copy()  # previous frame's measured local rotations
    prev_step = None  # and the measured local rotation step into it

    for f in range(first, F):
        has_meas = bool(frame_observed[f])
        accept = np.zeros(J, dtype=bool)  # may this block's filter update
        joint_ok = np.zeros(J, dtype=bool)  # is this joint's own measurement usable
        implausible = np.zeros(J, dtype=bool)
        gate_fail = np.zeros(J, dtype=bool)

        if has_meas:
            meas_pos = _world_positions(off[f], lq[f], ls[f], parents)

            # --- (a) the honesty test: is this measurement physically possible?
            # Second difference of the measured world positions over three
            # consecutive reconstructed frames is a * dt^2. Above A_MAX it is
            # not a limb, whatever the estimator says. Filter-independent on
            # purpose: it must not be possible for the smoother to hide a bad
            # estimate from its own honesty check.
            if prev_meas_pos is not None and prev_meas_f == f - 1:
                speed = np.linalg.norm(meas_pos - prev_meas_pos, axis=1)
                implausible = speed > (V_MAX_MPS * dt_nominal + GATE_NOISE_MARGIN_M)
                if prev2_meas_pos is not None:
                    d2 = np.linalg.norm(meas_pos - 2.0 * prev_meas_pos + prev2_meas_pos, axis=1)
                    implausible |= d2 > (A_MAX_MPS2 * dt_nominal**2 + GATE_NOISE_MARGIN_M)
                n_implausible += int(implausible.sum())

            # --- (b) the same test per block, in the block's own units, so
            # the filter can refuse the update rather than merely flag it.
            # A joint's local rotation moves everything below it, so its
            # measured angular step and angular acceleration become metres
            # once multiplied by the joint's lever arm, and the same V_MAX and
            # A_MAX apply. A leaf joint has lever 0 and is never gated, which
            # is right: rotating a leaf moves no joint at all.
            #
            # Measured from the estimator's own output, never from the
            # filter's state. Gating on the innovation against the filter's
            # prediction is the obvious design and it deadlocks: a held block
            # drifts away from the measurement, which inflates its own
            # innovation, which keeps it held. Measured on solo-01 that locked
            # the entire right leg into `uncertain` for all 296 frames and ate
            # 41% of the sub-3 Hz motion. A measurement-only test cannot form
            # that loop.
            dt_block = np.maximum(sample_times_s[f] - last_update_t, 1e-6)
            step = _rot_measurement(prev_lq, lq[f]) if prev_meas_f == f - 1 else None
            if step is not None:
                gate_fail = (lever * np.linalg.norm(step, axis=1)) > (
                    V_MAX_MPS * dt_nominal + GATE_NOISE_MARGIN_M
                )
                if prev_step is not None:
                    dev = np.linalg.norm(step - prev_step, axis=1)  # ~ alpha * dt^2, radians
                    gate_fail |= (lever * dev) > (A_MAX_MPS2 * dt_nominal**2 + GATE_NOISE_MARGIN_M)
                n_gated += int(gate_fail.sum())
            prev_step = step
            prev_lq = lq[f].copy()

            accept = (raw_sev[f] == OBSERVED) & ~gate_fail
            joint_ok = (raw_sev[f] == OBSERVED) & ~implausible
            n_skipped += int((raw_sev[f] != OBSERVED).sum())

            prev2_meas_pos, prev_meas_pos, prev_meas_f = prev_meas_pos, meas_pos, f

        # --- run the accepted blocks, skip the rest entirely ----------------
        # "Skip suppressed blocks entirely" (docs/TASKS.md W9) is implemented
        # literally: a suppressed block does not predict and does not update,
        # so its output holds its last filtered pose. Coasting on the
        # constant-velocity prediction instead is what a textbook filter does
        # with a missing measurement, and it is wrong here -- measured on
        # solo-01, joints with a real 25 rad/s angular velocity extrapolated
        # up to 177 degrees over three missing frames, inventing motion nobody
        # observed. A visible freeze is honest; an invented flourish is not.
        if has_meas and accept.any():
            # The scalars the filters see: the measurement expressed as a
            # tangent-space angle about each block's current nominal rotation.
            z = _rot_measurement(q_nom, lq[f])
            for j in np.flatnonzero(accept):
                if needs_reset[j]:
                    # Re-entry after a gap: restart this block at the new
                    # measurement with zero velocity rather than filtering
                    # across the hole (docs/PRD.md section 4).
                    q_nom[j] = lq[f, j]
                    for a in range(3):
                        rot_kf[j][a].x[:] = 0.0
                        rot_kf[j][a].P = np.diag([sigma[j, a] ** 2, (accel[j, a] * dt_nominal) ** 2])
                    needs_reset[j] = False
                    continue
                dtj = float(dt_block[j])
                dtheta_post = np.zeros(3)
                for a in range(3):
                    _set_dt(rot_kf[j][a], dtj, accel[j, a])
                    rot_kf[j][a].predict()
                    rot_kf[j][a].update(z[j, a])
                    dtheta_post[a] = rot_kf[j][a].x[0, 0]
                    # The error has been absorbed into the nominal quaternion
                    # below; reset the error state and keep the rate.
                    rot_kf[j][a].x[0, 0] = 0.0
                q_nom[j] = _rot_inject(q_nom[j][None], dtheta_post[None])[0]
            last_update_t[accept] = sample_times_s[f]

        # Reset is driven by absence of *evidence*, not by our own refusal to
        # use it: a block the gate rejected still had a real estimate behind
        # it and re-acquires through the filter, while a block with nothing to
        # look at for longer than the reset duration restarts cold. Restarting
        # means snapping to the first new measurement, which is honest after a
        # real gap and gratuitous after a rejected sample.
        no_evidence = (raw_sev[f] != OBSERVED) if has_meas else np.ones(J, dtype=bool)
        stale = np.where(no_evidence, stale + 1, 0)
        newly_frozen = (stale == max_hold_frames + 1) & ~needs_reset
        for j in np.flatnonzero(newly_frozen):
            for a in range(3):
                rot_kf[j][a].x[1, 0] = 0.0
        needs_reset |= newly_frozen

        # Root translation -- the one *translation* filter (every other offset
        # is a bone vector and belongs to the bone-constraints module).
        if has_meas and raw_sev[f, root] == OBSERVED:
            for a in range(3):
                _set_dt(trans_kf[a], float(dt_block[root]), trans_accel[a])
                trans_kf[a].predict()
                trans_kf[a].update(off[f, root, a])
        root_t = np.array([trans_kf[a].x[0, 0] for a in range(3)])

        # Bone offsets and scales pass through where the measurement is
        # usable, and hold where it is not.
        if has_meas and joint_ok.any():
            off_hold[joint_ok] = off[f, joint_ok]
            ls_hold[joint_ok] = ls[f, joint_ok]
        out_off[f] = off_hold
        out_off[f, root] = root_t
        out_ls[f] = ls_hold
        out_lq[f] = q_nom

        prov_obs[f] = frame_observed[f]
        # "interpolated" = no measurement from THIS frame reached this joint's
        # value; it came out of the filter. Deliberately not set for a
        # normally-filtered observed sample, which does carry this frame's
        # measurement (schema: "filled in ... across a gap rather than taken
        # directly from a single frame's estimate"). Flagged as a judgment
        # call in the W9 report -- the schema wording admits both readings.
        prov_interp[f] = ~(accept & joint_ok)
        # Everything the filter did instead of following the measurement has
        # to show up here, or the smoother has quietly manufactured
        # confidence (docs/DESIGN.md section 7h). Two ways that happens:
        # a measured sample that is not physically possible, and a block whose
        # update was refused -- the second one moves every joint below it, so
        # the descendant propagation below is what actually greys out the hand
        # hanging off a held elbow.
        bump = (implausible | gate_fail) & (raw_sev[f] < UNCERTAIN)
        raw_sev[f, bump] = UNCERTAIN
        raw_reason[f, bump] = LOW_CONFIDENCE

    # --- the leading gap ---------------------------------------------------
    # Back-fill from the first observed pose (same argument the exporter's
    # naive hold already makes -- a held pose plays as a visible freeze) but,
    # unlike the exporter, say so in the flags.
    for f in range(first):
        out_off[f] = off[first]
        out_lq[f] = lq[first]
        out_ls[f] = ls[first]
        prov_obs[f] = False
        prov_interp[f] = True

    # Gate failures only became known inside the loop; re-propagate so a bad
    # elbow still greys out the hand hanging off it, then debounce.
    raw_sev, raw_reason = _propagate_to_descendants(raw_sev, raw_reason, parents)
    vis, sup = _hysteresis(raw_sev, raw_reason)
    vis[:first] = np.maximum(vis[:first], UNCERTAIN)
    sup[:first] = np.where(sup[:first] == NOT_SUPPRESSED, LOW_CONFIDENCE, sup[:first])

    smoothed = recompose(out_off, out_lq, out_ls, parents)

    stats = {
        "n_frames": int(F),
        "n_observed_frames": int(frame_observed.sum()),
        "n_joints": int(J),
        "dt_s": dt_nominal,
        "innovation_gate_m": float(0.5 * A_MAX_MPS2 * dt_nominal**2 + GATE_NOISE_MARGIN_M),
        "implausible_gate_m": float(A_MAX_MPS2 * dt_nominal**2 + GATE_NOISE_MARGIN_M),
        "n_blocks_gated": int(n_gated),
        "n_samples_implausible": int(n_implausible),
        "n_updates_skipped_suppressed": int(n_skipped),
        "n_samples_uncertain": int((vis == UNCERTAIN).sum()),
        "n_samples_absent": int((vis == ABSENT).sum()),
        "n_samples_observed": int((vis == OBSERVED).sum()),
        "median_sigma_deg": float(np.degrees(np.median(sigma))),
        "median_accel_rad_s2": float(np.median(accel)),
    }
    return SmoothedTrack(
        skel_states=smoothed,
        visibility=vis,
        suppression=sup,
        prov_observed=prov_obs,
        prov_interpolated=prov_interp,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Orientation detours: the front/back (and left/right) flip
# ---------------------------------------------------------------------------
#
# SAM 3D Body sometimes turns the whole body round for a single frame and
# puts it back on the next -- the monocular front/back ambiguity, worst when
# the silhouette carries no facing cue (a hood up, back-lit, at night).
# Measured on job_a10682 (hoodie, night, 196 samples): at t=6.40 s the root
# swings 100 deg off the path between its neighbours, which themselves sit
# only 43 deg apart, the legs come back L/R-swapped, and the next frame
# returns. Every other detour across six lessons (2,509 samples) at spans
# of up to four samples stays at or under ~40 deg. Real turns -- including
# a10682's own full 360 at 3.0-4.1 s -- never trip it, because a real turn
# moves along the path between its neighbours rather than away and back.
#
# The rule: a span of observed samples no longer than DETOUR_MAX_SPAN_S whose
# root orientation is more than DETOUR_MIN_DEG off the slerp between the two
# observed samples around it -- at every sample of the span -- and whose
# neighbours are closer to each other than half that detour (it came back;
# a fast spin does not). The span's pose is replaced by interpolating every
# joint's local rotation (slerp) and bone offset/scale (lerp) between those
# neighbours. The replaced samples are marked by the caller as interpolated,
# never observed.
#
# ponytail: a flip that persists longer than DETOUR_MAX_SPAN_S is left alone:
# with no "came back" there is no local evidence which side is the wrong one.
# The upgrade is a 2D tie-breaker from the detector's own shoulder/hip order
# or face keypoints -- RTMO shares the same hood ambiguity, so measure first.

DETOUR_MIN_DEG = 60.0  # measured: the one real flip is 100 deg, the worst non-flip 40 deg
DETOUR_MAX_SPAN_S = 0.2  # 3 samples at 15 fps; a "flicker", not a held pose


def find_orientation_detours(sample_times_s, root_quats, observed) -> np.ndarray:
    """(F,) bool: samples whose root orientation is a short-lived detour.

    `root_quats` is (F, 4) xyzw world rotations of the root joint, `observed`
    (F,) bool. Shortest spans are tried first, so one bad sample is never
    widened into its neighbours.
    """
    t = np.asarray(sample_times_s, dtype=np.float64)
    ok = np.asarray(observed, dtype=bool).copy()
    F = len(t)
    q = np.asarray(root_quats, dtype=np.float64).copy()
    q[~ok] = (0.0, 0.0, 0.0, 1.0)  # never read: brackets and spans must be observed
    rot = Rotation.from_quat(q)
    bad = np.zeros(F, dtype=bool)
    dt = float(np.median(np.diff(t))) if F > 1 else 1.0 / 15.0
    max_len = max(1, int(round(DETOUR_MAX_SPAN_S / dt)))
    for n in range(1, max_len + 1):
        for a in range(1, F - n):
            b = a + n  # exclusive end; neighbours are a-1 and b
            if not (ok[a - 1] and ok[b] and ok[a:b].all()) or bad[a - 1:b + 1].any():
                continue
            gap = rot[a - 1].inv() * rot[b]
            w = (t[a:b] - t[a - 1]) / (t[b] - t[a - 1])
            path = rot[a - 1] * Rotation.from_rotvec(np.outer(w, gap.as_rotvec()))
            dev = np.degrees((path.inv() * rot[a:b]).magnitude()).min()
            if dev > DETOUR_MIN_DEG and np.degrees(gap.magnitude()) < 0.5 * dev:
                bad[a:b] = True
    return bad


def repair_orientation_detours(sample_times_s, skel_states, observed, parents, root: int):
    """Replace each detour span's whole pose with the interpolation between
    its observed neighbours. Returns (repaired (F, J, 8) float32, (F,) bool mask).
    Unflagged samples come back byte-identical."""
    skel_states = np.asarray(skel_states)
    t = np.asarray(sample_times_s, dtype=np.float64)
    bad = find_orientation_detours(t, skel_states[:, root, 3:7], observed)
    out = skel_states.astype(np.float32, copy=True)
    if not bad.any():
        return out, bad
    off, lq, ls = decompose(skel_states, parents)
    idx = np.flatnonzero(bad)
    # contiguous runs -> (first, last)
    for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
        a, b = int(run[0]) - 1, int(run[-1]) + 1
        w = (t[run] - t[a]) / (t[b] - t[a])
        for j in range(lq.shape[1]):
            ra = Rotation.from_quat(lq[a, j])
            step = (ra.inv() * Rotation.from_quat(lq[b, j])).as_rotvec()
            lq[run, j] = (ra * Rotation.from_rotvec(np.outer(w, step))).as_quat()
        off[run] = off[a] + w[:, None, None] * (off[b] - off[a])
        ls[run] = ls[a] + w[:, None] * (ls[b] - ls[a])
        out[run] = recompose(off[run], lq[run], ls[run], parents)
    return out, bad


def repair_clip_orientation(result: dict, hierarchy: Optional[dict] = None) -> dict:
    """In place on `result["per_frame"]`: every consumer (GLB export,
    MotionResult, smoothing) reads `skel_state` from there. A repaired person
    keeps its estimate as `skel_state_raw` and gets `orientation_repaired`,
    which motion_result.py turns into interpolated/uncertain. Returns
    {track_id: [repaired sample indices]}."""
    hierarchy = hierarchy or load_joint_hierarchy()
    parents = np.array([j["parent_index"] for j in hierarchy["joints"]])
    root = int(hierarchy.get("root_joint_index", 1))
    per_frame = result["per_frame"]
    F, J = len(per_frame), len(parents)
    report = {}
    for track_id in result["confident_track_ids"]:
        track_id = int(track_id)
        skel = np.zeros((F, J, 8), dtype=np.float32)
        observed = np.zeros(F, dtype=bool)
        for i, frame in enumerate(per_frame):
            person = frame.get(track_id) if isinstance(frame, dict) else None
            if person is not None and "skel_state" in person:
                skel[i] = np.asarray(person["skel_state"], dtype=np.float32)
                observed[i] = True
        fixed, bad = repair_orientation_detours(result["sample_times_s"], skel, observed, parents, root)
        for i in np.flatnonzero(bad):
            person = per_frame[i][track_id]
            person["skel_state_raw"] = person["skel_state"]
            person["skel_state"] = fixed[i]
            person["orientation_repaired"] = True
        report[track_id] = np.flatnonzero(bad).tolist()
    return report


def smooth_clip_result(result: dict, hierarchy: Optional[dict] = None) -> dict:
    """Run the chain over every dancer in a `process_clip()` result.

    Takes and returns plain dicts of numpy arrays, so `process_clip.py` needs
    only one call, and so the verification harness
    (`evaluation/measure_smoothing.py`) measures exactly the code the pipeline
    runs rather than a re-implementation of it.

    Returns {track_id: {"skel_states", "visibility", "suppression",
    "prov_observed", "prov_interpolated", "stats"}}.
    """
    hierarchy = hierarchy or load_joint_hierarchy()
    parents = np.array([j["parent_index"] for j in hierarchy["joints"]])
    names = [j["name"] for j in hierarchy["joints"]]

    per_frame = result["per_frame"]
    raw_detections = result["raw_detections"]
    times = np.asarray(result["sample_times_s"], dtype=np.float64)
    width = int(result.get("frame_width") or 0)
    height = int(result.get("frame_height") or 0)
    F, J = len(per_frame), len(parents)

    out = {}
    for track_id in result["confident_track_ids"]:
        track_id = int(track_id)
        skel = np.zeros((F, J, 8))
        observed = np.zeros(F, dtype=bool)
        kps = np.full((F, 17, 3), np.nan)
        # The seam this module documents at `correction_m`: how far the upstream
        # bone-length constraint had to move each joint. Stays None when that
        # stage did not run, which is what "optional by design" means.
        corr = np.full((F, J), np.nan)
        saw_correction = False
        for i in range(F):
            person = per_frame[i].get(track_id) if isinstance(per_frame[i], dict) else None
            if person is not None and "skel_state" in person:
                skel[i] = np.asarray(person["skel_state"], dtype=np.float64)
                observed[i] = True
            if person is not None and "bone_length_correction_m" in person:
                corr[i] = np.asarray(person["bone_length_correction_m"], dtype=np.float64)
                saw_correction = True
            track_ids = raw_detections[i]["track_ids"].tolist()
            if track_id in track_ids:
                kps[i] = raw_detections[i]["keypoints"][track_ids.index(track_id)]

        conf = oof = None
        if width > 0 and height > 0:
            conf, oof = detector_joint_signals(kps, width, height, names, parents)
        track = smooth_track(times, skel, observed, parents,
                             joint_conf=conf, joint_out_of_frame=oof,
                             correction_m=corr if saw_correction else None)
        out[track_id] = {
            "skel_states": track.skel_states,
            "visibility": track.visibility,
            "suppression": track.suppression,
            "prov_observed": track.prov_observed,
            "prov_interpolated": track.prov_interpolated,
            "stats": track.stats,
        }
    return out
