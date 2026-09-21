"""Floor solve: where is the ground, and do we trust it enough to draw it?

Two separate problems, two separate functions, on purpose:

    1. detect_foot_contacts()  -- which (frame, foot) samples are evidence that
       a foot was ON the floor, and how strongly.  Returns a WEIGHT in [0, 1]
       per sample, not a boolean, so a learned per-frame contact model (WHAM/
       GVHMR-style, if one ever lands here with a compatible licence) can drop
       in as a probability without touching anything downstream.
    2. fit_floor_plane()       -- given weighted candidate points, the plane.

They fail in completely different ways (1 fails by calling the apex of a jump a
contact; 2 fails by fitting a plane through the wrong consensus set), so they
are independently testable and independently replaceable.  `solve_grounding`
takes `contact_detector` as an argument for exactly that reason.

CORE-ALGORITHM NOTE (docs/AGENT-BRIEFS.md standing rule 5 reserves grounding
for the builder): `detect_foot_contacts` and `fit_floor_plane` are the two
functions the builder may want to rewrite.  Everything else here -- the
coordinate-frame plumbing, the honesty thresholds, the contract fragment -- is
scaffolding around them.  Swapping either one means replacing one function with
the same signature; nothing else in the pipeline knows how they work.

COORDINATE FRAME.  Everything in this module is in the contract's world space:
metres, Y-up, the same frame `MotionResult.root_trajectory[].position` uses and
the same frame the exported GLB uses.  Concretely that is `skel_state`'s own
character-local frame divided by 100 (skel_state is centimetres; pymomentum's
save_gltf_from_skel_states already converts to metres on export -- verified by
reading a real exported GLB's root node translation, 0.92399 m, against the
same clip's skel_state root translation, 92.399 cm).

Why NOT camera space, which is the frame with a physically real floor in it:
`pred_cam_t` is per-crop weak-perspective depth.  Measured on solo-01, its z
component correlates -0.93 with detector bbox height and swings 3.2 m -> 10.9 m
across a clip where the dancer barely travels, and the resulting foot positions
correlate 0.98 between y and z -- i.e. they lie along the viewing ray, which is
a degenerate configuration for plane fitting (infinitely many planes contain a
line).  Fitting there would produce a confident number from an unconstrained
estimate, which is the exact failure mode DESIGN.md section 7h exists to
prevent.  The character-local frame is camera-ALIGNED (body_world carries
identity rotation every frame; global orientation lives in the root joint), so
a floor plane fitted here is still a real plane in a real orientation -- it
just has the dancer's horizontal travel removed, which the export does not
carry anyway.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np

# Foot joints below the ankle, from the real MHR 127-joint skeleton
# (services/motion-api/mhr_joint_hierarchy.json).  The contact candidate for a
# foot in a frame is the LOWEST of these, not a fixed joint: a heel-down step
# and a toe-down step contact the floor with different bones.
FOOT_JOINTS: dict[str, tuple[str, ...]] = {
    "left": ("l_talocrural", "l_subtalar", "l_transversetarsal", "l_ball"),
    "right": ("r_talocrural", "r_subtalar", "r_transversetarsal", "r_ball"),
}
FOOT_ORDER = ("left", "right")

# COCO-17 ankle indices in the detector's keypoints (RTMO, to_openpose=False).
# COCO "left" is the person's left, same convention as MHR's l_ prefix.  This
# mapping only decides WHICH foot a visibility flag applies to; the honest-none
# gate below requires both ankles visible, so a left/right mix-up cannot turn a
# "none" into a "grounded".
COCO_ANKLE = {"left": 15, "right": 16}

# ---------------------------------------------------------------------------
# Thresholds.  Every one of these is a product decision with a number attached,
# not a tuned constant -- the whole point of this module is that "grounded" is
# a claim the product makes, and a wrong "grounded" is worse than an honest
# "none" (DESIGN.md section 10 forbids faking a plane at all).  Measured values
# for the clip are always reported in diagnostics so these can be re-tuned
# against evidence rather than re-guessed.
# ---------------------------------------------------------------------------

# A foot is "visible" if the detector's ankle keypoint for it beat this score
# and landed inside the frame.  0.3 is well below RTMO's own 0.7 default (which
# process_clip already lowers to 0.1 for ByteTrack's sake) and well above the
# 0.006-0.03 floor scores seen on genuinely-missing ankles in real solo-01
# frames; measured solo-01 ankle scores are 0.98 median, so this threshold is
# nowhere near the working range and only fires on real absence.
ANKLE_SCORE_MIN = 0.3

# "Enough of the clip", in one number, used by both evidence gates below.
# PRD section 4 says "none" is correct when the feet were "cropped/occluded for
# enough of the clip that a floor fit is not trustworthy" and never says what
# enough is; this does.  A floor is a claim about the WHOLE clip, so it has to
# be evidenced across most of the clip -- 0.6 is "most", deliberately a round
# product number rather than a tuned one, and every clip's measured value is
# reported in diagnostics so it can be re-set against evidence later.
MIN_CLIP_EVIDENCE_FRACTION = 0.6

# Gate 1, measured in FRAMES: could we see the feet at all?  This is the gate
# evaluation/clips.yaml's stress-cropped-feet (a Short framed from the knees
# up) is aimed at, and that case sits at ~0.0, nowhere near the threshold.
MIN_FOOT_VISIBLE_FRACTION = MIN_CLIP_EVIDENCE_FRACTION

# Half-thickness of the RANSAC consensus band, metres.  3 cm is about a shoe
# sole plus per-frame joint noise, and 1.8% of a 1.7 m body -- tight enough
# that a foot in the air cannot join the consensus, loose enough to survive
# normal reconstruction jitter.
CONTACT_TOL_M = 0.03

# Minimum number of inlier contact samples.  Three non-collinear points define
# a plane EXACTLY, so residual-based quality checks are meaningless below about
# six samples -- a sparse fit is guaranteed to look perfect.  12 samples is 4x
# redundancy and, at 15 fps, about 0.8 s of real contact evidence.
MIN_CONTACT_INLIERS = 12

# Inlier RMS ceiling, metres.  A consensus set can be large and still be
# rubbish if the band is doing all the work; this checks the fit is actually
# tight inside the band rather than filling it.
MAX_INLIER_RMS_M = 0.02

# Gate 2, measured in SECONDS: did the feet actually reach the fitted plane,
# across the clip?  Fraction of the clip's RECONSTRUCTED seconds that must
# contain at least one contact inlier.  The denominator is every second in which a
# dancer existed, not every second in which their feet happened to be visible:
# with the narrower denominator a half-cropped clip scores well by shrinking
# its own exam (measured -- solo-07 with its second half's ankles blanked
# invented a floor 0.94 m up, because the evidence covered most of what was
# left).  This is the gate that the real measurements forced into existence:
# on solo-01 the plane fits beautifully (1.45 cm RMS, 27 inliers) off evidence
# that is almost entirely in the clip's first two seconds, and the figure then
# hovers a median 0.125 m above it for the rest.  Inlier count and RMS cannot
# see that; only the distribution of the evidence in time can.  0.6 means "for
# most of this clip the floor is where the feet actually are"; below it, the
# floor is an extrapolation over the majority of the clip's duration, which is
# a claim the product has no evidence for.
MIN_CONTACT_TIME_COVERAGE = MIN_CLIP_EVIDENCE_FRACTION

# Maximum tilt of the fitted normal from +Y, degrees.  The MVP input assumption
# is one front camera, mostly steady (PRD section 5), and the frame here is
# camera-aligned, so a floor more than 25 degrees off horizontal means either
# the camera assumption broke or the consensus set is wrong.  Either way the
# honest answer is "none", not a tilted stage.
MAX_TILT_DEG = 25.0

# Tilt cap for the CAMERA-SPACE solve (solve_grounding_camera_space) -- NOT a
# relaxed MAX_TILT_DEG.  MAX_TILT_DEG's justification ("more than 25 degrees
# off horizontal means the camera-steady assumption broke") is specific to the
# OLD character-local frame, where body_world carries identity rotation every
# frame and the floor SHOULD sit near +Y if the phone was held upright.
# Solving directly in the camera's own space removes that assumption: real
# floors measured on solo-01/solo-07/group-synced-01 sit 13-18 degrees off +Y
# because the phone was lying near the ground pointing up, which is a fact
# about how these clips were filmed, not a broken assumption -- see
# docs/research/world-placement.md.  That measured range would clear either
# threshold; this one is wider on purpose because there is no steadiness
# assumption left to violate here, short of the camera pointing mostly
# sideways or down at the dancer instead of at the floor.
CAMERA_SPACE_MAX_TILT_DEG = 35.0

# Contact-heuristic knobs (defaults for detect_foot_contacts; they belong to
# the heuristic, not to the honesty decision, so a replacement detector is free
# to ignore them).
CONTACT_HEIGHT_BAND_M = 0.06  # how far above the low envelope still counts
CONTACT_MAX_SPEED_MPS = 0.30  # vertical speed at which the weight reaches 0
LOW_ENVELOPE_PERCENTILE = 5.0  # bootstrap guess at floor height


@dataclass(frozen=True)
class FootTrack:
    """One dancer's foot evidence over the clip, in contract world space."""

    points: np.ndarray  # (F, 2, 3) lowest foot joint per (frame, foot)
    valid: np.ndarray  # (F, 2) bool -- reconstructed AND ankle visible
    reconstructed: np.ndarray  # (F,) bool -- the dancer was reconstructed at all


@dataclass(frozen=True)
class PlaneFit:
    normal: np.ndarray  # (3,) unit, oriented +Y-ish
    point: np.ndarray  # (3,) a point on the plane
    inliers: np.ndarray  # (N,) bool, over the points passed in
    rms_m: float  # weighted RMS distance of inliers to the plane
    tilt_deg: float  # angle between normal and +Y


def _signed_distance(points: np.ndarray, origin: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Point-to-plane signed distance, written as an explicit product rather
    than `@`: a gemv through Apple's Accelerate BLAS raises spurious
    divide-by-zero/overflow FP flags on perfectly finite inputs, and a numpy
    RuntimeWarning in a pipeline log is indistinguishable from a real one."""
    return ((points - origin) * normal).sum(axis=-1)


ContactDetector = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]
"""(points (F,2,3), valid (F,2), times_s (F,)) -> weights (F,2) in [0,1].

The seam a learned per-frame foot-contact model plugs into.  It may return
hard 0/1 or a calibrated probability; fit_floor_plane consumes the weights
either way.
"""


# ---------------------------------------------------------------------------
# Seam 1: which samples are contact evidence.  REPLACEABLE.
# ---------------------------------------------------------------------------

def detect_foot_contacts(
    points: np.ndarray,
    valid: np.ndarray,
    times_s: np.ndarray,
    *,
    height_band_m: float = CONTACT_HEIGHT_BAND_M,
    max_speed_mps: float = CONTACT_MAX_SPEED_MPS,
    low_envelope_percentile: float = LOW_ENVELOPE_PERCENTILE,
) -> np.ndarray:
    """Weight every (frame, foot) sample by how much it looks like a contact.

    Two terms, multiplied, because either one alone is wrong in a way the other
    fixes:

    * HEIGHT, relative to the clip's own low envelope.  Alone it would accept a
      foot passing through floor level at speed mid-step.
    * VERTICAL SPEED.  Alone it would accept the apex of a jump, where vertical
      velocity is exactly zero and the foot is half a metre up.

    Deliberately NOT a classifier: this is a geometric prior over data that has
    already been reconstructed, and it is the default implementation of the
    ContactDetector seam, not the only possible one.

    ponytail: linear ramps, no hysteresis, no per-foot state machine.  The
    plane fit that consumes these is a robust estimator whose job is to survive
    a noisy weighting; sharpening the weights buys much less than it costs.
    Upgrade path is replacing the whole function, not adding terms to it.
    """
    points = np.asarray(points, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    times_s = np.asarray(times_s, dtype=np.float64)
    heights = points[:, :, 1]

    weights = np.zeros_like(heights)
    if not valid.any():
        return weights

    floor_guess = float(np.percentile(heights[valid], low_envelope_percentile))
    w_height = np.clip(1.0 - (heights - floor_guess) / height_band_m, 0.0, 1.0)

    # Vertical speed by one-sided differences against the nearest valid
    # neighbour in each direction, so a gap in the track does not manufacture a
    # huge velocity across it (and does not silently interpolate across it
    # either -- a sample with no valid neighbour gets weight 0, never a
    # fabricated "it was still, so it must have been planted").
    speed = np.full_like(heights, np.inf)
    for foot in range(heights.shape[1]):
        idx = np.flatnonzero(valid[:, foot])
        if idx.size < 2:
            continue
        dh = np.gradient(heights[idx, foot], times_s[idx])
        speed[idx, foot] = np.abs(dh)
    w_speed = np.clip(1.0 - speed / max_speed_mps, 0.0, 1.0)

    weights = np.where(valid, w_height * w_speed, 0.0)
    return weights


# ---------------------------------------------------------------------------
# Seam 2: the plane.  REPLACEABLE.
# ---------------------------------------------------------------------------

def fit_floor_plane(
    points: np.ndarray,
    weights: np.ndarray,
    *,
    tol_m: float = CONTACT_TOL_M,
    max_tilt_deg: float = MAX_TILT_DEG,
    iterations: int = 400,
    seed: int = 0,
) -> Optional[PlaneFit]:
    """Weighted RANSAC + weighted least-squares refit.  None if no consensus.

    Why RANSAC and not plain least squares, Theil-Sen, or a low quantile:

    * The outliers here are not noise, they are FEET IN THE AIR -- a large,
      one-sided population up to 0.4 m off the floor (measured on solo-01).
      Least squares is dragged upward by them by construction.
    * A quantile / lower-envelope fit also survives them, but it has to assume
      what fraction of the clip is contact, and that fraction is wildly
      clip-dependent (standing choreography vs solo-07's floor work).  RANSAC
      assumes only that the contacts are the largest self-consistent set.
    * The tilt prior is enforced on every hypothesis, not just the winner, so a
      steep consensus set can never win by being bigger.

    Sampling is weight-proportional, and the refit is weight-aware, so a
    probabilistic contact detector's confidence reaches the geometry instead of
    being thresholded away first.

    ponytail: no guard on the horizontal SPREAD of the consensus set. A dancer
    who never moves their feet gives contacts clustered in one spot, where the
    tilt is unconstrained and can be anything up to `max_tilt_deg`. Measured
    spread is fine on both real clips (0.54 m x, 0.48 m z on solo-01, and the
    tilted fit genuinely beats a horizontal one there: 27 inliers vs 21), and
    the viewer currently uses only `point[1]`, so a wrong tilt costs nothing
    today. Add a spread guard if the normal ever drives rendering.
    """
    points = np.asarray(points, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    keep = weights > 0
    if keep.sum() < 3:
        return None

    idx_pool = np.flatnonzero(keep)
    probs = weights[idx_pool] / weights[idx_pool].sum()
    rng = np.random.default_rng(seed)
    cos_max = np.cos(np.deg2rad(max_tilt_deg))

    best_score, best_normal, best_origin = -1.0, None, None
    for _ in range(iterations):
        trio = rng.choice(idx_pool, size=3, replace=False, p=probs)
        a, b, c = points[trio]
        normal = np.cross(b - a, c - a)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:  # collinear sample
            continue
        normal = normal / norm
        if normal[1] < 0:
            normal = -normal
        if normal[1] < cos_max:  # too steep to be this product's floor
            continue
        dist = np.abs(_signed_distance(points, a, normal))
        inliers = (dist <= tol_m) & keep
        score = float(weights[inliers].sum())
        if score > best_score:
            best_score, best_normal, best_origin = score, normal, a

    if best_normal is None:
        return None

    # Weighted least-squares refit on the consensus set: the RANSAC winner is
    # defined by three samples, which is a fine hypothesis and a poor estimate.
    inliers = (np.abs(_signed_distance(points, best_origin, best_normal)) <= tol_m) & keep
    w = weights[inliers]
    pts = points[inliers]
    centroid = (w[:, None] * pts).sum(0) / w.sum()
    centred = (pts - centroid) * np.sqrt(w)[:, None]
    _, _, vh = np.linalg.svd(centred, full_matrices=False)
    normal = vh[-1]
    if normal[1] < 0:
        normal = -normal

    dist = _signed_distance(points, centroid, normal)
    inliers = (np.abs(dist) <= tol_m) & keep
    if inliers.sum() < 3:
        return None
    w = weights[inliers]
    rms = float(np.sqrt((w * dist[inliers] ** 2).sum() / w.sum()))
    tilt = float(np.rad2deg(np.arccos(np.clip(normal[1], -1.0, 1.0))))
    return PlaneFit(normal=normal, point=centroid, inliers=inliers, rms_m=rms, tilt_deg=tilt)


# ---------------------------------------------------------------------------
# The honesty decision.  Scaffolding around the two seams above.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GroundingResult:
    grounding: dict  # the MotionResult.grounding fragment, contract-shaped
    diagnostics: dict  # everything measured, for logs and reports -- NOT in the contract
    evidence: dict  # raw arrays for a follow-on world-placement solve (see below)
    """`evidence` exists so the next piece of work -- placing the dancer in the
    room, which this deliberately does NOT do (OPEN-DECISIONS E6) -- does not
    have to re-derive any of it:

        plane            the PlaneFit, PRESENT EVEN WHEN THE VERDICT IS "none".
                         A refused plane is still the best floor estimate
                         available; it is refused as a product claim, not as a
                         number. None only if no plane could be fitted at all.
        contact_weights  list of (F, 2) arrays, one per track, index-aligned
                         with the `tracks` argument: per-frame, per-foot
                         contact weight in [0, 1].
        contact_points   list of (F, 2, 3) arrays, the points those weights
                         refer to, in the same world space as the plane.
        foot_valid       list of (F, 2) bool arrays: was this foot visible.
    """


def _none(reason: str, diagnostics: dict, evidence: dict) -> GroundingResult:
    diagnostics["reason"] = reason
    return GroundingResult({"status": "none", "floor_plane": None}, diagnostics, evidence)


def solve_grounding(
    tracks: Sequence[FootTrack],
    times_s: np.ndarray,
    *,
    contact_detector: ContactDetector = detect_foot_contacts,
    min_visible_fraction: float = MIN_FOOT_VISIBLE_FRACTION,
    min_inliers: int = MIN_CONTACT_INLIERS,
    min_time_coverage: float = MIN_CONTACT_TIME_COVERAGE,
    max_rms_m: float = MAX_INLIER_RMS_M,
    max_tilt_deg: float = MAX_TILT_DEG,
    tol_m: float = CONTACT_TOL_M,
) -> GroundingResult:
    """Decide `grounded` vs `none`, and produce the plane when grounded.

    Contact detection runs per dancer (it needs a continuous time series);
    the plane fit runs once for the clip over every dancer's evidence pooled,
    since there is one floor and more evidence is a better floor.

    Every exit is a "no" until the evidence earns a "yes".  In order:
      1. feet visible in at least `min_visible_fraction` of reconstructed frames
      2. at least 3 weighted contact candidates to fit anything at all
      3. a consensus plane exists within the tilt prior
      4. at least `min_inliers` inlier samples
      5. inlier RMS within `max_rms_m`
      6. tilt within `max_tilt_deg`
      7. contact evidence covers at least `min_time_coverage` of the clip's
         usable seconds -- a floor supported only by the first two seconds is
         an extrapolation over the rest, not a measurement of it
    """
    times_s = np.asarray(times_s, dtype=np.float64)
    diagnostics: dict = {
        "n_tracks": len(tracks),
        "thresholds": {
            "min_visible_fraction": min_visible_fraction,
            "min_inliers": min_inliers,
            "min_time_coverage": min_time_coverage,
            "max_rms_m": max_rms_m,
            "max_tilt_deg": max_tilt_deg,
            "contact_tol_m": tol_m,
        },
    }

    n_reconstructed = sum(int(t.reconstructed.sum()) for t in tracks)
    n_both_visible = sum(int((t.valid.all(axis=1) & t.reconstructed).sum()) for t in tracks)
    visible_fraction = (n_both_visible / n_reconstructed) if n_reconstructed else 0.0
    diagnostics.update(
        n_reconstructed_frames=n_reconstructed,
        n_both_feet_visible_frames=n_both_visible,
        foot_visible_fraction=round(visible_fraction, 4),
    )
    # Built before the first gate returns, so a refused clip still hands a
    # follow-on solve everything it measured (see GroundingResult.evidence).
    evidence: dict = {
        "plane": None,
        "contact_weights": [],
        "contact_points": [t.points for t in tracks],
        "foot_valid": [t.valid for t in tracks],
    }
    all_points, all_weights, all_times = [], [], []
    clip_seconds: set = set()
    for track in tracks:
        w = np.asarray(contact_detector(track.points, track.valid, times_s), dtype=np.float64)
        evidence["contact_weights"].append(w)
        all_points.append(track.points.reshape(-1, 3))
        all_weights.append(w.reshape(-1))
        all_times.append(np.repeat(times_s, track.points.shape[1]))
        clip_seconds |= set(np.floor(times_s[track.reconstructed]).astype(int).tolist())

    if visible_fraction < min_visible_fraction:
        return _none("feet_not_visible_enough", diagnostics, evidence)
    points = np.concatenate(all_points) if all_points else np.zeros((0, 3))
    weights = np.concatenate(all_weights) if all_weights else np.zeros((0,))
    point_times = np.concatenate(all_times) if all_times else np.zeros((0,))
    diagnostics.update(
        n_contact_candidates=int((weights > 0).sum()),
        total_contact_weight=round(float(weights.sum()), 3),
    )
    if (weights > 0).sum() < 3:
        return _none("no_contact_evidence", diagnostics, evidence)

    fit = fit_floor_plane(points, weights, tol_m=tol_m, max_tilt_deg=max_tilt_deg)
    if fit is None:
        return _none("no_consensus_plane", diagnostics, evidence)
    # Kept even if a gate below refuses it: a refused plane is still the best
    # floor estimate there is, refused as a product claim rather than as a number.
    evidence["plane"] = fit

    n_inliers = int(fit.inliers.sum())
    covered_seconds = set(np.floor(point_times[fit.inliers]).astype(int).tolist()) & clip_seconds
    coverage = len(covered_seconds) / max(1, len(clip_seconds))
    # How far the body's lowest foot actually sits above the fitted plane,
    # over every frame the feet were visible.  This is the number that says
    # whether the render will look grounded; it is reported whatever the
    # verdict, because "grounded with a 0.12 m median gap" is exactly the
    # confidently-wrong output DESIGN.md section 7h exists to prevent.
    gaps = []
    for track in tracks:
        ok = track.valid.all(axis=1) & track.reconstructed
        if not ok.any():
            continue
        gaps.append(_signed_distance(track.points[ok], fit.point, fit.normal).min(axis=1))
    gap = np.concatenate(gaps) if gaps else np.zeros(0)
    diagnostics.update(
        n_inliers=n_inliers,
        inlier_rms_m=round(fit.rms_m, 5),
        tilt_deg=round(fit.tilt_deg, 3),
        floor_height_m=round(float(fit.point[1]), 4),
        contact_time_coverage=round(coverage, 4),
        clip_seconds=len(clip_seconds),
        covered_seconds=len(covered_seconds),
        lowest_foot_gap_median_m=round(float(np.median(gap)), 4) if gap.size else None,
        lowest_foot_gap_p95_m=round(float(np.percentile(gap, 95)), 4) if gap.size else None,
        planted_frame_fraction=round(float((np.abs(gap) <= tol_m).mean()), 4) if gap.size else None,
    )
    if n_inliers < min_inliers:
        return _none("too_few_contacts", diagnostics, evidence)
    if fit.rms_m > max_rms_m:
        return _none("fit_too_loose", diagnostics, evidence)
    if fit.tilt_deg > max_tilt_deg:
        return _none("implausible_tilt", diagnostics, evidence)
    if coverage < min_time_coverage:
        return _none("contacts_not_spread_over_clip", diagnostics, evidence)

    diagnostics["reason"] = "grounded"
    return GroundingResult(
        {
            "status": "grounded",
            "floor_plane": {
                "normal": [round(float(v), 6) for v in fit.normal],
                "point": [round(float(v), 6) for v in fit.point],
            },
        },
        diagnostics,
        evidence,
    )


# ---------------------------------------------------------------------------
# Pipeline plumbing: npz -> FootTrack.  Boring on purpose.
# ---------------------------------------------------------------------------

def foot_tracks_from_clip(
    per_frame: Sequence[dict],
    raw_detections: Sequence[dict],
    track_ids: Sequence[int],
    joint_names: Sequence[str],
    frame_width: int = 0,
    frame_height: int = 0,
    *,
    ankle_score_min: float = ANKLE_SCORE_MIN,
) -> list[FootTrack]:
    """Pull foot evidence out of what run_clip already saved to the npz.

    Visibility comes from the DETECTOR's ankle keypoints, not from the
    reconstruction: SAM 3D Body always returns a full 127-joint body for a
    crop, including for joints it never saw, so its own output cannot tell you
    a foot was out of frame.  RTMO's per-keypoint score can, and it is the same
    signal that would be missing on a knees-up clip.
    """
    name_to_idx = {name: i for i, name in enumerate(joint_names)}
    foot_idx = [[name_to_idx[n] for n in FOOT_JOINTS[side] if n in name_to_idx] for side in FOOT_ORDER]
    if any(len(g) == 0 for g in foot_idx):
        raise ValueError("joint_names has no MHR foot joints -- wrong skeleton?")

    n = len(per_frame)
    tracks = []
    for track_id in track_ids:
        points = np.zeros((n, 2, 3), dtype=np.float64)
        valid = np.zeros((n, 2), dtype=bool)
        reconstructed = np.zeros(n, dtype=bool)
        for i in range(n):
            frame = per_frame[i]
            person = frame.get(track_id) if isinstance(frame, dict) else None
            if person is None or "skel_state" not in person:
                continue
            reconstructed[i] = True
            # skel_state is centimetres, Y-up; the contract's world space is
            # metres, Y-up (api.py applies the same /100 to root_trajectory).
            joints_m = np.asarray(person["skel_state"], dtype=np.float64)[:, :3] / 100.0
            ankle_scores = _ankle_scores(raw_detections[i], track_id, frame_width, frame_height)
            for f in range(2):
                group = joints_m[foot_idx[f]]
                points[i, f] = group[np.argmin(group[:, 1])]
                valid[i, f] = ankle_scores[f] >= ankle_score_min
        tracks.append(FootTrack(points=points, valid=valid, reconstructed=reconstructed))
    return tracks


def _ankle_scores(detection: dict, track_id: int, frame_width: int, frame_height: int) -> tuple[float, float]:
    """Per-foot detector ankle confidence, zeroed if the keypoint is outside
    the frame (a confidently-extrapolated ankle below the bottom edge is
    exactly the cropped-feet case, and it is not evidence of anything)."""
    if detection is None:
        return (0.0, 0.0)
    ids = np.asarray(detection.get("track_ids", []))
    hits = np.flatnonzero(ids == track_id)
    if hits.size == 0:
        return (0.0, 0.0)
    kps = np.asarray(detection["keypoints"])[hits[0]]
    out = []
    for side in FOOT_ORDER:
        x, y, score = kps[COCO_ANKLE[side]]
        if frame_width and not (0 <= x < frame_width):
            score = 0.0
        if frame_height and not (0 <= y < frame_height):
            score = 0.0
        out.append(float(score))
    return (out[0], out[1])


def camera_intrinsics_from_clip(npz_data) -> Optional[dict]:
    """The clip's real pinhole intrinsics, contract-shaped, or None.

    Not used by the floor solve (which works in the metric character-local
    frame and never touches the camera). It lives here because it is the one
    thing a follow-on world-placement solve needs that nobody had written down,
    and because the projection model below was established by measurement:

        u = fx * X / Z + cx,  v = fy * Y / Z + cy,  (cx, cy) = image centre

    reproduces the estimator's own `pred_keypoints_2d` from
    `pred_keypoints_3d + pred_cam_t` with a **median error of 0.00 px** on real
    solo-07 output -- and 277.78 px if the principal point is taken at the crop
    bbox centre, which is the obvious wrong guess. `focal_length` in the npz is
    the pipeline's own FOV estimate, exactly constant per clip (one unique
    value across all 291 solo-01 / 436 solo-07 person records), so it is a
    per-clip calibration and not a per-frame wobble.
    """
    focals = [
        float(person["focal_length"])
        for frame in npz_data["per_frame"]
        if isinstance(frame, dict)
        for person in frame.values()
        if "focal_length" in person
    ]
    width = int(npz_data["frame_width"]) if "frame_width" in npz_data else 0
    height = int(npz_data["frame_height"]) if "frame_height" in npz_data else 0
    if not focals or not width or not height:
        return None
    focal = float(np.median(focals))
    return {
        "fx": focal,
        "fy": focal,
        "cx": width / 2.0,
        "cy": height / 2.0,
        "reference_width_px": width,
        "reference_height_px": height,
    }


def solve_grounding_for_clip(npz_data, joint_names: Sequence[str], **kwargs) -> GroundingResult:
    """One call from a loaded run_clip npz to the contract fragment."""
    tracks = foot_tracks_from_clip(
        per_frame=npz_data["per_frame"],
        raw_detections=npz_data["raw_detections"],
        track_ids=npz_data["confident_track_ids"].tolist(),
        joint_names=joint_names,
        frame_width=int(npz_data["frame_width"]) if "frame_width" in npz_data else 0,
        frame_height=int(npz_data["frame_height"]) if "frame_height" in npz_data else 0,
    )
    return solve_grounding(tracks, npz_data["sample_times_s"], **kwargs)


# ---------------------------------------------------------------------------
# Camera-space grounding (docs/research/world-placement.md, OPEN-DECISIONS E6).
#
# foot_tracks_from_clip above works in the character-local frame, which has no
# depth in it -- global translation is flattened to a per-clip constant, so a
# floor fit there is a real plane but built from feet that never actually
# travelled. world_placement_probe.place_track solves the per-frame camera-
# space translation that frame is missing (rigid skeleton + per-frame 3-DoF
# PnP against the detector's own keypoints + a 5-frame median filter). The
# functions below take that solve's output and feed it through the SAME
# honesty decision (solve_grounding), just with real per-frame depth in the
# evidence instead of a flattened one.
# ---------------------------------------------------------------------------

# camera space (world_placement_probe: X-right, Y-DOWN, Z-forward) -> contract
# world space (X-right, Y-up, Z-forward): negate Y and Z, a handedness-
# preserving 180-degree rotation about X. The same flip
# skeleton_constraints.constrain_clip's `jc_to_ss` already applies to get from
# pred_joint_coords to skel_state's world-space translation (verified there
# against a real exported GLB), applied once here at the point camera-space
# output is consumed.
_CAMERA_TO_WORLD_FLIP = np.array([1.0, -1.0, -1.0])

# Reused, not re-derived: world_placement_probe.probe() already declines a
# track from its own printed floor summary when it clears place_track's
# 25-frame minimum (enough evidence to place the body at all) but still has
# too few geometrically-on-the-floor contact candidates to trust -- this is
# exactly solo-07 track 3's case (48 frames, but short/distant with almost no
# usable contacts). Same threshold probe() uses for both numbers: 12 contacts
# (MIN_CONTACT_INLIERS -- the same redundancy bar fit_floor_plane itself
# requires) at weight > 0.05.
_POOL_MIN_CONTACTS = MIN_CONTACT_INLIERS
_POOL_MIN_CONTACT_WEIGHT = 0.05


def _passes_pool_evidence_gate(placement: Optional[dict]) -> bool:
    """Clearing world_placement_probe.place_track's own 25-frame gate (it got
    placed at all) is not the same question as whether its feet should be
    pooled into the SHARED floor fit -- a short/distant track can clear the
    first and fail the second. `placement` is None (never placed) or one
    `world_placement_probe.place_track` return dict."""
    if placement is None:
        return False
    good = np.isfinite(placement["feet"]).all(axis=2) & (placement["contact_w"] > _POOL_MIN_CONTACT_WEIGHT)
    return int(good.sum()) >= _POOL_MIN_CONTACTS


def foot_tracks_from_camera_space(placements: Sequence[Optional[dict]], n_samples: int) -> list[FootTrack]:
    """`FootTrack`s built from world_placement_probe's camera-space solve,
    converted once into contract world space, instead of foot_tracks_from_clip's
    character-local (no-travel) frame.

    `placements[i]` is `world_placement_probe.place_track(data, track_id)`'s
    return value for the i-th confidently-tracked dancer -- or None, either
    because that track never cleared place_track's own 25-frame minimum, or
    because a caller has already declined it via `_passes_pool_evidence_gate`
    (a None placement contributes no evidence here; it does not affect the
    "were feet visible" denominator either).
    """
    tracks = []
    for placement in placements:
        points = np.zeros((n_samples, 2, 3), dtype=np.float64)
        valid = np.zeros((n_samples, 2), dtype=bool)
        reconstructed = np.zeros(n_samples, dtype=bool)
        if placement is not None:
            idx = np.asarray(placement["idx"])
            feet_world = np.asarray(placement["feet"], dtype=np.float64) * _CAMERA_TO_WORLD_FLIP
            ok = np.isfinite(feet_world).all(axis=2)
            vis = np.asarray(placement["visible"], dtype=bool)
            points[idx] = np.where(ok[:, :, None], feet_world, 0.0)
            valid[idx] = ok & vis
            reconstructed[idx] = True
        tracks.append(FootTrack(points=points, valid=valid, reconstructed=reconstructed))
    return tracks


def _camera_space_contact_detector(weights_by_track: Sequence[np.ndarray]) -> ContactDetector:
    """Adapts world_placement_probe.image_contact_weights's per-track output
    (already computed by place_track, from real image-space foot speed and
    real depth) into the ContactDetector seam, instead of re-running
    detect_foot_contacts's world-space height/speed heuristic on the composed
    points. This is the exact evidence world-placement.md's floor-inlier
    numbers (52% -> 90% on solo-01) were measured against.

    solve_grounding calls the detector once per track, in the same order as
    the `tracks` list it was given -- relied on here via iteration order, so
    the two lists this is paired with (from foot_tracks_from_camera_space)
    must be built from the same `placements` list. A mismatched call count
    raises StopIteration rather than silently pairing the wrong track.
    """
    it = iter(weights_by_track)

    def _detector(points: np.ndarray, valid: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        return next(it)

    return _detector


def _pooled_weight_array(placement: Optional[dict], n_samples: int) -> np.ndarray:
    w = np.zeros((n_samples, 2), dtype=np.float64)
    if placement is not None:
        w[np.asarray(placement["idx"])] = placement["contact_w"]
    return w


def solve_grounding_camera_space(
    placements: Sequence[Optional[dict]],
    times_s,
    n_samples: int,
    *,
    max_tilt_deg: float = CAMERA_SPACE_MAX_TILT_DEG,
    **kwargs,
) -> GroundingResult:
    """One call from a list of world_placement_probe.place_track results to
    the contract fragment, real per-frame depth instead of the flattened
    character-local frame foot_tracks_from_clip/solve_grounding_for_clip use.

    `placements[i]` is `world_placement_probe.place_track(data, track_id)` for
    the i-th confidently-tracked dancer, or None if that track had fewer than
    25 frames. Every other gate (MIN_CLIP_EVIDENCE_FRACTION, MIN_CONTACT_INLIERS,
    MAX_INLIER_RMS_M, ...) is unchanged, via solve_grounding's own defaults;
    only the tilt cap and the evidence source differ.
    """
    pooled = [p if _passes_pool_evidence_gate(p) else None for p in placements]
    tracks = foot_tracks_from_camera_space(pooled, n_samples)
    weights = [_pooled_weight_array(p, n_samples) for p in pooled]
    detector = _camera_space_contact_detector(weights)
    return solve_grounding(tracks, times_s, contact_detector=detector, max_tilt_deg=max_tilt_deg, **kwargs)


if __name__ == "__main__":  # measurement tool: python grounding.py <clip.npz>
    import json
    import sys
    from pathlib import Path

    hierarchy = json.loads((Path(__file__).resolve().parent / "mhr_joint_hierarchy.json").read_text())
    names = [j["name"] for j in hierarchy["joints"]]
    for path in sys.argv[1:]:
        data = np.load(path, allow_pickle=True)
        result = solve_grounding_for_clip(data, names)
        print(f"\n=== {path}")
        print(json.dumps(result.grounding, indent=2))
        print(json.dumps(result.diagnostics, indent=2))
