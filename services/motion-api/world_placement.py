"""World placement: where in the room is each dancer, on every frame.

E6. The reconstruction hands us a body with no world position at all --
`skel_state`'s root row is the same eight numbers on every frame of every clip
(measured: exactly `[0,0,0, 0,0,0,1, 1]` across all 291 reconstructed frames of
solo-01). The pose is there; the placement is missing. This module supplies it,
so `root_trajectory` is a measurement instead of a constant and `grounding.py`
gets foot positions in a frame where a floor can actually be fitted.

WHAT PINS THE DEPTH -- and what does not.

Three candidate constraints, only one of which works:

1. *The floor.* Intersecting a contact foot's image ray with the ground plane
   looks like it should fix depth, and it does not. With the per-frame depth
   `d_f` unknown AND the plane `(n, c)` unknown, each contact frame contributes
   one equation, `n . (foot_f + d_f * ray_f) = c`, and one new unknown `d_f`.
   The plane's three degrees of freedom stay free no matter how many contact
   frames there are: *any* plane admits a consistent set of depths. The floor
   cannot pin depth and depth cannot pin the floor. Do not re-derive this.

2. *Apparent size* -- how big the metric body looks. This is what SAM 3D Body's
   `pred_cam_t` uses, and on its own it is unreliable: it reads every pose error
   as a distance change, and a dancer who gets low reads as a dancer who moved
   away. Used alone it slides the body on every crouch.

3. *A planted foot does not move.* THIS is the constraint that works, and it
   comes from outside both the floor and the reconstruction. If a foot is in
   contact on frame f and again on frame f+1, its world position is the same on
   both, which ties those two frames' translations together directly. Chain that
   across a clip and the depth of every contact-linked frame is pinned relative
   to its neighbours; apparent size then only has to supply the overall level,
   which is the one thing it is adequate for.

So the solve is ONE weighted linear least squares over every frame's translation
at once (not a per-frame solve), with three kinds of row:

  * reprojection -- the placed body must project onto the DETECTOR's keypoints
    (RTMO's COCO-17, an independent measurement, not the reconstruction's own
    re-projection of itself),
  * contact -- a planted ankle must not move between consecutive frames,
  * a light acceleration penalty, which is a noise model for keypoint jitter and
    nothing more. It is not a motion prior and is weak enough to be overridden.

Contact probability is NOT re-implemented here. It comes from
`grounding.detect_foot_contacts`, the seam that module documents as replaceable,
so a learned contact model drops into both places at once.

WHAT THIS CANNOT MEASURE, and the honest consequence (DESIGN.md section 7h).

The focal length. Measured directly by re-running this whole solve across a 3x
focal sweep on solo-01: median reprojection error moved only 10.2 -> 11.2 px and
the contact slip and floor RMS did not move at all, while the depth extent of the
recovered travel scaled almost exactly linearly with the assumed focal (4.6 m at
0.6x, 13.7 m at 1.8x). The clip simply does not contain the information; the
dancer is small enough in frame that the reconstruction sits in the weak
perspective regime where focal and depth trade off one for one. Source video
carries no lens metadata either (checked: the eval clips are re-encoded social
video with the EXIF stripped).

What that costs, precisely: the recovered world is correct up to an unknown
uniform STRETCH ALONG THE CAMERA'S VIEW AXIS. Everything measured parallel to
the image plane is unaffected, and so -- measured, not assumed -- is the floor
fit: across that same 3x sweep the floor RMS stayed at 1.3-1.5 cm and the camera
height above the floor moved only 0.19 -> 0.23 m. Lateral travel, foot-to-floor
contact, jumps leaving and landing on the plane: all sound. How far
front-to-back the dancer actually travelled: scaled by an unknown factor near 1.
`intrinsics.fx` is therefore reported as the focal the reconstruction itself
assumed (the image diagonal), which is a stated prior, not a calibration -- see
`Diagnostics["focal_source"]`, and E6's entry in docs/OPEN-DECISIONS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from grounding import (
    COCO_ANKLE,
    FOOT_JOINTS,
    FOOT_ORDER,
    ContactDetector,
    FootTrack,
    detect_foot_contacts,
    fit_floor_plane,
)

# RTMO gives COCO-17; the reconstruction gives MHR70. The first 15 MHR70 names
# are COCO's own names in COCO's own order (verified against
# sam_3d_body/metadata/mhr70.py) EXCEPT that MHR70 puts the wrists at 41/62
# instead of 9/10, so only those two need looking up.
COCO_TO_MHR70 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 62, 41, 9, 10, 11, 12, 13, 14])

# A keypoint below this detector score is not evidence. Same threshold and same
# reasoning as grounding.ANKLE_SCORE_MIN -- well below RTMO's own default, well
# above the 0.006-0.03 seen on genuinely-absent joints.
SCORE_MIN = 0.3

# Residual weights, all expressed as "how wrong is this allowed to be", so they
# are readable as tolerances rather than as tuning knobs.
SIGMA_PX = 5.0           # a detector keypoint is trusted to about 5 px
# How far a PLANTED foot may drift between two consecutive frames. This is the
# single most consequential number in the module and it has to be small, because
# it is a per-PAIR tolerance and therefore a random-walk allowance: at 2 cm a
# frame, a systematic drift of exactly 2 cm a frame is free, which over a 20
# frame hold is 40 cm of sliding that costs the solve nothing. Measured on the
# synthetic crouch scene: at 0.02 the held span still drifted 0.52 m, at 0.005
# it is flat. 5 mm still leaves room for the real heel-to-toe roll of a foot
# that is genuinely planted.
SIGMA_SLIP_M = 0.005
SIGMA_ACC_M = 0.05       # keypoint-jitter noise model, per frame^2

# Bootstrap-only: before any floor is known, foot samples are fitted with a loose
# band purely to find which way is up. The real floor fit is grounding.py's, at
# its own 3 cm tolerance.
BOOTSTRAP_TOL_M = 0.10
BOOTSTRAP_MAX_TILT_DEG = 60.0

MIN_KEYPOINTS = 6        # fewer than this and the frame's 3 unknowns are guesswork
MIN_CONTACT_WEIGHT = 0.05
SOLVE_ITERATIONS = 3

# A track with fewer contact links than this had nothing holding its depth, so
# its trajectory is apparent size alone -- which is the estimator this module
# exists to stop trusting. Same number and the same reasoning as grounding.py's
# MIN_CONTACT_INLIERS: below about a dozen samples there is no redundancy, so a
# confident-looking answer is just the sampling noise. Such tracks are returned
# UNPLACED (NaN) rather than placed badly; the caller then falls back to the
# pinned, honestly-flagged pose. Measured: this drops the 6-frame and 7-frame
# passer-by fragments in group-synced-01, which were being handed 2 m of
# invented depth travel off zero contact evidence.
MIN_TRACK_CONTACT_LINKS = 12


@dataclass(frozen=True)
class ClipPlacement:
    """Everything the contract needs that this module is responsible for."""

    camera_to_world: list  # 16 floats, column-major, metres (Camera.camera_to_world)
    intrinsics: dict       # Camera.intrinsics
    root_positions: dict   # track_id -> (F, 3) world metres, NaN where unplaced
    foot_tracks: list      # list[FootTrack], world space -- feed to solve_grounding
    diagnostics: dict = field(default_factory=dict)


def _yup(points: np.ndarray) -> np.ndarray:
    """OpenCV camera convention (Y down, Z forward) -> Y up, same origin.

    `pred_joint_coords` and `pred_keypoints_3d` are in the camera convention;
    everything downstream of here (and all of grounding.py) is Y-up. Verified
    against the same clip's `skel_state`: pred_joint_coords == (x, -y, -z) *
    skel_state[:, :3] / 100, exactly.
    """
    points = np.asarray(points, dtype=np.float64)
    return np.stack([points[..., 0], -points[..., 1], -points[..., 2]], axis=-1)


def _basis_from_normal(normal: np.ndarray) -> np.ndarray:
    """Right-handed rotation whose +Y is `normal`. Rows are the world axes."""
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    seed = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(seed, n))) > 0.9:
        seed = np.array([1.0, 0.0, 0.0])
    z_axis = seed - float(np.dot(seed, n)) * n
    z_axis /= np.linalg.norm(z_axis)
    return np.stack([np.cross(n, z_axis), n, z_axis])


class _Track:
    """One dancer's per-frame evidence, in the frames it was reconstructed in."""

    def __init__(self, joints, model_2d3d, observed_2d, reconstructed, focal, times):
        self.joints = joints            # (F, 127, 3) camera convention, root-relative
        self.model = model_2d3d         # (F, 17, 3) same, COCO-ordered
        self.observed = observed_2d     # (F, 17, 3) detector x, y, score
        self.reconstructed = reconstructed
        self.focal = focal
        self.times = times


def _load_track(npz_data, track_id: int, width: int, height: int, joint_names) -> Optional[_Track]:
    per_frame = npz_data["per_frame"]
    raw = npz_data["raw_detections"]
    n = len(per_frame)
    joints = np.full((n, len(joint_names), 3), np.nan)
    model = np.full((n, 17, 3), np.nan)
    observed = np.full((n, 17, 3), np.nan)
    reconstructed = np.zeros(n, dtype=bool)
    focal = None
    for i in range(n):
        frame = per_frame[i]
        person = frame.get(track_id) if isinstance(frame, dict) else None
        if person is None or "pred_joint_coords" not in person:
            continue
        detection = raw[i]
        ids = np.asarray(detection.get("track_ids", []))
        hit = np.flatnonzero(ids == track_id)
        if hit.size == 0:
            # Reconstructed but untracked this frame: no independent 2D
            # measurement, so no placement. Left NaN rather than guessed.
            continue
        reconstructed[i] = True
        focal = float(person["focal_length"])
        joints[i] = np.asarray(person["pred_joint_coords"], dtype=np.float64)
        model[i] = np.asarray(person["pred_keypoints_3d"], dtype=np.float64)[COCO_TO_MHR70]
        keypoints = np.asarray(detection["keypoints"], dtype=np.float64)[hit[0]].copy()
        # Off-frame keypoints are extrapolations by the detector, not sightings.
        outside = (
            (keypoints[:, 0] < 0) | (keypoints[:, 0] >= width)
            | (keypoints[:, 1] < 0) | (keypoints[:, 1] >= height)
        )
        keypoints[outside, 2] = 0.0
        observed[i] = keypoints
    if focal is None:
        return None
    return _Track(joints, model, observed, reconstructed, focal,
                  np.asarray(npz_data["sample_times_s"], dtype=np.float64))


def _reprojection_rows(model, observed, focal, cx, cy):
    """Rows of `project(P + t) == m`, linear in t.

    With x = (u - cx)/f, the perspective equation x * (Pz + tz) == Px + tx is
    already linear -- no iteration needed, and no Gauss-Newton to converge.
    """
    visible = np.flatnonzero(observed[:, 2] > SCORE_MIN)
    if visible.size < MIN_KEYPOINTS:
        return None
    P = model[visible]
    x = (observed[visible, 0] - cx) / focal
    y = (observed[visible, 1] - cy) / focal
    n = visible.size
    A = np.zeros((2 * n, 3))
    b = np.zeros(2 * n)
    A[0::2, 0] = -1.0
    A[0::2, 2] = x
    A[1::2, 1] = -1.0
    A[1::2, 2] = y
    b[0::2] = P[:, 0] - x * P[:, 2]
    b[1::2] = P[:, 1] - y * P[:, 2]
    return A, b, np.repeat(observed[visible, 2], 2)


def _per_frame_pnp(track: _Track, cx: float, cy: float) -> np.ndarray:
    """Independent per-frame translation. Bootstrap for the global solve only."""
    n = len(track.reconstructed)
    out = np.full((n, 3), np.nan)
    for i in np.flatnonzero(track.reconstructed):
        rows = _reprojection_rows(track.model[i], track.observed[i], track.focal, cx, cy)
        if rows is None:
            continue
        A, b, w = rows
        sw = np.sqrt(w)
        out[i], *_ = np.linalg.lstsq(A * sw[:, None], b * sw, rcond=None)
    return out


def _foot_points(track: _Track, translations, foot_idx, rotation=None):
    """(F, 2, 3) lowest joint of each foot, plus per-foot validity."""
    n = len(track.reconstructed)
    points = np.zeros((n, 2, 3))
    valid = np.zeros((n, 2), dtype=bool)
    usable = track.reconstructed & np.isfinite(translations).all(axis=1)
    for i in np.flatnonzero(usable):
        world = _yup(track.joints[i] + translations[i])
        if rotation is not None:
            world = world @ rotation.T
        for k in range(2):
            group = world[foot_idx[k]]
            points[i, k] = group[np.argmin(group[:, 1])]
            valid[i, k] = track.observed[i, COCO_ANKLE[FOOT_ORDER[k]], 2] > SCORE_MIN
    return points, valid & usable[:, None]


def _frame_fit(tracks, translations, foot_idx):
    """The clip's floor, used ONLY to define the world frame.

    Chicken-and-egg dodge: contact detection needs heights, heights need a
    floor, a floor needs contacts. Broken by fitting a plane through ALL foot
    samples with uniform weight and a loose band -- no height notion required,
    because feet spend most of a clip near the floor, so the largest
    self-consistent set of foot positions IS the floor.

    Deliberately NOT contact-weighted, though that sounds more accurate.
    Measured on solo-01: contact weighting shrinks the sample set to the frames
    the current placement already believes are planted, which is a feedback loop
    -- swept across slip tolerances it moved the recovered camera height from
    -0.67 m (below its own floor, i.e. nonsense) to +0.98 m and swung
    grounding.py's verdict with it. Uniform weights over every visible foot
    sample are stable because they cannot be steered by the placement.

    This fit decides the frame, never the product: whether the floor is
    trustworthy enough to draw is grounding.py's call, made separately on the
    placed points with its own 3 cm tolerance and its own honesty gates.
    """
    points, weights = [], []
    for track, T in zip(tracks, translations):
        pts, valid = _foot_points(track, T, foot_idx)
        points.append(pts.reshape(-1, 3))
        weights.append(valid.reshape(-1).astype(float))
    return fit_floor_plane(
        np.concatenate(points), np.concatenate(weights),
        tol_m=BOOTSTRAP_TOL_M, max_tilt_deg=BOOTSTRAP_MAX_TILT_DEG,
    )


def _rough_up(tracks, translations, foot_idx) -> np.ndarray:
    fit = _frame_fit(tracks, translations, foot_idx)
    return np.array([0.0, 1.0, 0.0]) if fit is None else fit.normal


def _global_solve(track: _Track, initial, contact, ankle_idx, cx, cy):
    """One least squares over every frame's translation at once.

    ponytail: dense normal equations, O(F^3) in the frame count. At the PRD's
    60 s / 15 fps cap that is a 2700x2700 solve -- under a second, and the
    coupling is only ever to the next frame, so the upgrade path if the cap ever
    rises is a block-tridiagonal Thomas solve over the same matrix, not a
    different formulation.
    """
    index = np.flatnonzero(track.reconstructed & np.isfinite(initial).all(axis=1))
    if index.size < 2:
        return initial, 0
    slot = {int(i): k for k, i in enumerate(index)}
    size = 3 * index.size
    normal_matrix = np.zeros((size, size))
    gradient = np.zeros(size)

    def accumulate(entries, rhs, weight):
        rows = [3 * s + axis for s, axis, _ in entries]
        coeffs = np.array([c for _, _, c in entries], dtype=np.float64)
        normal_matrix[np.ix_(rows, rows)] += weight * np.outer(coeffs, coeffs)
        gradient[rows] += weight * rhs * coeffs

    # 1. the placed body must project onto the detector's keypoints. Residuals
    # are algebraic (metres at unit depth), so each is scaled by (f/z)^2 to put
    # it back in pixels before being compared against SIGMA_PX.
    for i in index:
        rows = _reprojection_rows(track.model[i], track.observed[i], track.focal, cx, cy)
        if rows is None:
            continue
        A, b, w = rows
        s = slot[int(i)]
        depth = max(float(initial[i, 2]), 0.5)
        scale = (track.focal / depth) ** 2 / SIGMA_PX ** 2
        for r in range(A.shape[0]):
            entries = [(s, axis, A[r, axis]) for axis in range(3) if A[r, axis] != 0.0]
            accumulate(entries, b[r], w[r] * scale)

    # 2. a planted foot does not move between consecutive frames. The ankle, not
    # the lowest joint, because which joint is lowest flips between a heel-down
    # and a toe-down step and that flip is not motion.
    links = 0
    for a, b in zip(index[:-1], index[1:]):
        if b != a + 1:
            continue
        for k in range(2):
            weight = min(float(contact[a, k]), float(contact[b, k]))
            if weight <= MIN_CONTACT_WEIGHT:
                continue
            links += 1
            pa = track.joints[a, ankle_idx[k]]
            pb = track.joints[b, ankle_idx[k]]
            for axis in range(3):
                accumulate(
                    [(slot[int(b)], axis, 1.0), (slot[int(a)], axis, -1.0)],
                    float(pa[axis] - pb[axis]), weight / SIGMA_SLIP_M ** 2,
                )

    # 3. keypoint-noise model. Weak on purpose: it must never be able to smooth
    # away real travel, only per-frame jitter.
    for a, b, c in zip(index[:-2], index[1:-1], index[2:]):
        if b != a + 1 or c != b + 1:
            continue
        for axis in range(3):
            accumulate(
                [(slot[int(a)], axis, 1.0), (slot[int(b)], axis, -2.0), (slot[int(c)], axis, 1.0)],
                0.0, 1.0 / SIGMA_ACC_M ** 2,
            )

    normal_matrix[np.diag_indices_from(normal_matrix)] += 1e-9
    solution = np.linalg.solve(normal_matrix, gradient).reshape(-1, 3)
    out = np.full_like(initial, np.nan)
    out[index] = solution
    return out, links


def place_clip(
    npz_data,
    joint_names: Sequence[str],
    *,
    contact_detector: ContactDetector = detect_foot_contacts,
) -> Optional[ClipPlacement]:
    """Place every confidently-tracked dancer in one shared world frame.

    Returns None when the clip carries nothing to place (no reconstruction, or
    no frame size to build intrinsics from) -- the caller then keeps the
    unplaced, honestly-flagged fallback rather than receiving an invented one.
    """
    width = int(npz_data["frame_width"]) if "frame_width" in npz_data else 0
    height = int(npz_data["frame_height"]) if "frame_height" in npz_data else 0
    if not width or not height:
        return None
    cx, cy = width / 2.0, height / 2.0

    name_to_idx = {name: i for i, name in enumerate(joint_names)}
    foot_idx = [[name_to_idx[n] for n in FOOT_JOINTS[s] if n in name_to_idx] for s in FOOT_ORDER]
    if any(len(g) == 0 for g in foot_idx):
        raise ValueError("joint_names has no MHR foot joints -- wrong skeleton?")
    ankle_idx = [foot_idx[0][0], foot_idx[1][0]]  # *_talocrural, first in FOOT_JOINTS
    root_idx = name_to_idx.get("root", 0)

    track_ids = [int(t) for t in npz_data["confident_track_ids"]]
    tracks, ids = [], []
    for track_id in track_ids:
        track = _load_track(npz_data, track_id, width, height, joint_names)
        if track is not None:
            tracks.append(track)
            ids.append(track_id)
    if not tracks:
        return None

    translations = [_per_frame_pnp(t, cx, cy) for t in tracks]
    links_total = 0
    for _ in range(SOLVE_ITERATIONS):
        rotation = _basis_from_normal(_rough_up(tracks, translations, foot_idx))
        links_total = 0
        for k, track in enumerate(tracks):
            points, valid = _foot_points(track, translations[k], foot_idx, rotation)
            contact = contact_detector(points, valid, track.times)
            translations[k], links = _global_solve(
                track, translations[k], contact, ankle_idx, cx, cy)
            links_total += links

    # One floor for the clip, every dancer pooled -- same principle as
    # solve_grounding, and the reason a two-dancer clip is a free consistency
    # check.
    frame_fit = _frame_fit(tracks, translations, foot_idx)
    if frame_fit is None:
        # No consensus about which way is up -- happens when a dancer never
        # moves their feet, so every foot sample is one point and any plane
        # fits. The TRAJECTORY is still real and is still returned; only the
        # world's orientation is unknown, so the camera's own up axis is used
        # and said so. grounding.py then judges the floor on its own evidence
        # and will refuse it on the tilt gate if this guess was wrong -- which
        # is the honest outcome, and better than discarding the placement.
        rotation, floor_offset, oriented = np.eye(3), 0.0, False
    else:
        rotation = _basis_from_normal(frame_fit.normal)
        floor_offset = float((rotation @ frame_fit.point)[1])
        oriented = True

    def to_world(camera_points):
        world = _yup(camera_points) @ rotation.T
        world[..., 1] -= floor_offset
        return world

    foot_tracks, root_positions = [], {}
    for track_id, track, T in zip(ids, tracks, translations):
        n = len(track.reconstructed)
        points = np.zeros((n, 2, 3))
        valid = np.zeros((n, 2), dtype=bool)
        placed = np.zeros(n, dtype=bool)
        roots = np.full((n, 3), np.nan)
        for i in np.flatnonzero(track.reconstructed & np.isfinite(T).all(axis=1)):
            placed[i] = True
            world = to_world(track.joints[i] + T[i])
            roots[i] = world[root_idx]
            for k in range(2):
                group = world[foot_idx[k]]
                points[i, k] = group[np.argmin(group[:, 1])]
                valid[i, k] = track.observed[i, COCO_ANKLE[FOOT_ORDER[k]], 2] > SCORE_MIN
        foot_tracks.append(FootTrack(points=points, valid=valid & placed[:, None],
                                     reconstructed=placed))
        root_positions[track_id] = roots

    # camera_to_world: camera (OpenCV) -> Y-up -> world. diag(1,-1,-1) is a
    # proper rotation, so `rotation @ flip` is too.
    flip = np.diag([1.0, -1.0, -1.0])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation @ flip
    matrix[:3, 3] = [0.0, -floor_offset, 0.0]

    travel = {}
    for track_id, roots in root_positions.items():
        good = roots[np.isfinite(roots).all(axis=1)]
        travel[track_id] = [round(float(v), 3) for v in (np.ptp(good, axis=0) if good.size else np.zeros(3))]

    return ClipPlacement(
        # Contract says column-major; numpy is row-major, hence the transpose.
        camera_to_world=[float(v) for v in matrix.T.reshape(-1)],
        intrinsics={
            "fx": float(tracks[0].focal),
            "fy": float(tracks[0].focal),
            "cx": cx,
            "cy": cy,
            "reference_width_px": width,
            "reference_height_px": height,
        },
        root_positions=root_positions,
        foot_tracks=foot_tracks,
        diagnostics={
            "focal_px": round(float(tracks[0].focal), 2),
            # Named so nobody downstream can mistake a prior for a calibration.
            "focal_source": "reconstruction_prior_image_diagonal",
            "world_oriented": oriented,
            "camera_height_above_floor_m": round(-floor_offset, 4),
            "frame_floor_tilt_deg": round(float(frame_fit.tilt_deg), 3) if oriented else None,
            "contact_links": int(links_total),
            "root_travel_xyz_m": travel,
        },
    )
