"""Tests for the floor solve. Pure numpy, no GPU, no Modal, no fixtures.

The most important test in this file is `test_cropped_feet_reports_none` (and
its real-data twin at the bottom): evaluation/clips.yaml's `stress-cropped-feet`
slot has a NEGATIVE success criterion -- grounding must report "none" and no
fake floor. Everything else here exists to make sure that "none" is a decision
and not just the module failing to work at all.

    python3 -m pytest services/motion-api/test_grounding.py -q
"""
import json
import os
from pathlib import Path

import numpy as np
import pytest

import grounding as g

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads(
    (HERE.parent.parent / "packages" / "motion-contract" / "schema" / "motion-result.schema.json").read_text()
)


# --------------------------------------------------------------------------- helpers

def synth_clip(
    n_frames=300,
    fps=15.0,
    floor_y=0.05,
    tilt_deg=0.0,
    step_hz=1.5,
    lift_m=0.25,
    drift_after=None,
    drift_m=0.25,
    visible=True,
    noise_m=0.004,
    seed=1,
):
    """A dancer stepping in place on a known plane.

    Feet alternate: one planted on the plane, the other lifted on a half-sine.
    From frame `drift_after` on, BOTH feet are displaced upward by `drift_m` --
    which is the real solo-01 failure in miniature: the character-local
    vertical datum rides the pelvis, so a plié lifts the whole body off its own
    floor and contact evidence stops.
    """
    rng = np.random.default_rng(seed)
    times = np.arange(n_frames) / fps
    drift_after = n_frames if drift_after is None else drift_after
    tilt = np.deg2rad(tilt_deg)
    normal = np.array([0.0, np.cos(tilt), -np.sin(tilt)])
    origin = np.array([0.0, floor_y, 0.0])

    points = np.zeros((n_frames, 2, 3))
    for i in range(n_frames):
        phase = (times[i] * step_hz) % 1.0
        for f in range(2):
            x = -0.12 if f == 0 else 0.12
            z = 0.35 * np.sin(2 * np.pi * times[i] * 0.3)  # some travel, so tilt is observable
            # plane height at (x, z): solve normal . (p - origin) = 0 for y
            y = origin[1] - (normal[0] * (x - origin[0]) + normal[2] * (z - origin[2])) / normal[1]
            if (phase < 0.5) == (f == 0):  # this foot is the swinging one
                y += lift_m * np.sin(np.pi * ((phase * 2) % 1.0))
            if i >= drift_after:
                y += drift_m
            points[i, f] = (x, y, z)
    points += rng.normal(0, noise_m, points.shape)
    valid = np.full((n_frames, 2), bool(visible))
    reconstructed = np.ones(n_frames, dtype=bool)
    return g.FootTrack(points, valid, reconstructed), times, normal, origin


# --------------------------------------------------------------------------- the fitter

def test_fit_recovers_a_known_tilted_plane():
    track, times, normal, origin = synth_clip(tilt_deg=8.0, floor_y=0.05)
    weights = g.detect_foot_contacts(track.points, track.valid, times)
    fit = g.fit_floor_plane(track.points.reshape(-1, 3), weights.reshape(-1))
    assert fit is not None
    assert np.degrees(np.arccos(abs(float(fit.normal @ normal)))) < 3.0, "normal off by >3 deg"
    height_err = abs(float(g._signed_distance(origin, fit.point, fit.normal)))
    assert height_err < 0.02, f"floor height off by {height_err:.3f} m"


def test_fit_is_not_dragged_up_by_feet_in_the_air():
    """The whole reason for a robust estimator: airborne feet are a large,
    one-sided outlier population, not symmetric noise."""
    track, times, _, origin = synth_clip(floor_y=0.05, lift_m=0.30)
    weights = g.detect_foot_contacts(track.points, track.valid, times)
    fit = g.fit_floor_plane(track.points.reshape(-1, 3), weights.reshape(-1))
    naive = float(track.points[:, :, 1].mean())  # plain least squares on every foot sample
    assert abs(float(fit.point[1]) - origin[1]) < 0.02
    assert abs(naive - origin[1]) > 0.05, "test is not exercising the outlier population"


def test_fit_respects_the_tilt_prior():
    """A wall is never this product's floor, however good the consensus."""
    rng = np.random.default_rng(0)
    pts = rng.normal(0, 0.3, (200, 3))
    pts[:, 0] = 0.0  # a perfect vertical plane, x = 0
    fit = g.fit_floor_plane(pts, np.ones(len(pts)))
    assert fit is None or fit.tilt_deg <= g.MAX_TILT_DEG


def test_fit_consumes_weights_not_just_a_filtered_subset():
    """A learned detector may hand back probabilities. Down-weighting (rather
    than dropping) a wrong cluster must still move the answer."""
    grid = np.linspace(-0.3, 0.3, 7)
    xs, zs = np.meshgrid(grid, grid)
    good = np.column_stack([xs.ravel(), np.full(xs.size, 0.05), zs.ravel()])
    bad = good + np.array([0.0, 0.40, 0.0])
    pts = np.vstack([good, bad])
    n = len(good)
    # Same points, same count in each cluster: only the weights differ, so the
    # answer must follow them.
    trust_low = np.concatenate([np.ones(n), np.full(n, 0.05)])
    trust_high = np.concatenate([np.full(n, 0.05), np.ones(n)])
    assert abs(float(g.fit_floor_plane(pts, trust_low).point[1]) - 0.05) < 0.01
    assert abs(float(g.fit_floor_plane(pts, trust_high).point[1]) - 0.45) < 0.01


# --------------------------------------------------------------------------- the detector

def test_contact_detector_rejects_the_apex_of_a_jump():
    """Vertical velocity alone would call the apex a contact: it is the one
    moment in a jump where dy/dt is exactly zero."""
    times = np.arange(60) / 15.0
    height = 0.5 * np.sin(np.pi * np.arange(60) / 59.0)  # up and down, apex mid-clip
    pts = np.zeros((60, 2, 3))
    pts[:, :, 1] = height[:, None]
    pts[:5, :, 1] = 0.0  # a genuine plant at the start
    w = g.detect_foot_contacts(pts, np.ones((60, 2), bool), times)
    apex = int(np.argmax(height))
    assert w[apex].max() == 0.0, "apex of a jump scored as contact"
    assert w[1:4].max() > 0.5, "a planted, stationary foot scored as non-contact"


def test_contact_weights_are_bounded_and_zero_where_invalid():
    track, times, _, _ = synth_clip(n_frames=90)
    valid = track.valid.copy()
    valid[30:60] = False
    w = g.detect_foot_contacts(track.points, valid, times)
    assert w.min() >= 0.0 and w.max() <= 1.0
    assert not w[30:60].any()


# --------------------------------------------------------------------------- the decision

def _grounding_matches_contract(fragment):
    spec = SCHEMA["$defs"]["Grounding"]
    assert set(fragment) == set(spec["required"]), fragment
    assert fragment["status"] in spec["properties"]["status"]["enum"]
    # The invariant the schema states in prose and the product depends on.
    assert (fragment["floor_plane"] is None) == (fragment["status"] == "none")
    if fragment["floor_plane"] is not None:
        assert set(fragment["floor_plane"]) == {"normal", "point"}
        assert len(fragment["floor_plane"]["normal"]) == 3
        assert fragment["floor_plane"]["normal"][1] > 0, "normal must point up (+Y-ish)"


def test_a_clean_clip_is_grounded_and_contract_shaped():
    track, times, _, origin = synth_clip(floor_y=0.05)
    result = g.solve_grounding([track], times)
    _grounding_matches_contract(result.grounding)
    assert result.grounding["status"] == "grounded", result.diagnostics
    assert abs(result.grounding["floor_plane"]["point"][1] - origin[1]) < 0.02
    assert result.diagnostics["planted_frame_fraction"] > 0.5


def test_cropped_feet_reports_none():
    """evaluation/clips.yaml's stress-cropped-feet: a Short framed from the
    knees up. THE SUCCESS CRITERION IS NEGATIVE -- no floor may be invented."""
    track, times, _, _ = synth_clip(visible=False)
    result = g.solve_grounding([track], times)
    _grounding_matches_contract(result.grounding)
    assert result.grounding["status"] == "none"
    assert result.grounding["floor_plane"] is None
    assert result.diagnostics["reason"] == "feet_not_visible_enough"


def test_partly_cropped_feet_flips_at_the_stated_threshold():
    """The threshold is a product decision, so it has to actually be the
    threshold -- not a value the code drifts away from."""
    n = 300
    for visible_fraction, expected in ((0.95, "grounded"), (0.7, "grounded"), (0.55, "none"), (0.2, "none")):
        track, times, _, _ = synth_clip(n_frames=n)
        valid = track.valid.copy()
        valid[int(n * visible_fraction):] = False  # feet leave the frame partway through
        result = g.solve_grounding([g.FootTrack(track.points, valid, track.reconstructed)], times)
        assert result.grounding["status"] == expected, (visible_fraction, result.diagnostics)


def test_contacts_bunched_at_the_start_report_none():
    """Real failure mode, found on solo-01: a plane can fit 27 samples at
    1.45 cm RMS and still describe only the first two seconds of the clip."""
    track, times, _, _ = synth_clip(n_frames=300, drift_after=45)
    result = g.solve_grounding([track], times)
    assert result.grounding["status"] == "none"
    assert result.diagnostics["reason"] == "contacts_not_spread_over_clip"
    assert result.diagnostics["contact_time_coverage"] < g.MIN_CONTACT_TIME_COVERAGE


def test_no_dancer_at_all_reports_none_rather_than_crashing():
    empty = g.FootTrack(np.zeros((30, 2, 3)), np.zeros((30, 2), bool), np.zeros(30, bool))
    result = g.solve_grounding([empty], np.arange(30) / 15.0)
    _grounding_matches_contract(result.grounding)
    assert result.grounding["status"] == "none"


def test_a_replacement_contact_detector_drops_in():
    """The seam a learned per-frame contact model plugs into: same signature,
    probabilities rather than a heuristic, nothing else changes."""
    track, times, _, origin = synth_clip(floor_y=0.05)

    def oracle(points, valid, times_s):  # pretend learned model
        near = points[:, :, 1] < (origin[1] + 0.02)
        return np.where(valid & near, 0.9, 0.0)

    result = g.solve_grounding([track], times, contact_detector=oracle)
    assert result.grounding["status"] == "grounded"
    assert abs(result.grounding["floor_plane"]["point"][1] - origin[1]) < 0.02


# --------------------------------------------------------------------------- real data

REAL_NPZ = os.environ.get("STEPWISE_NPZ", "/tmp/stepwise-grounding/solo-01.npz")


@pytest.mark.skipif(not Path(REAL_NPZ).exists(), reason=f"no real clip npz at {REAL_NPZ}")
def test_cropped_feet_on_a_real_clip_reports_none():
    """The synthesized `stress-cropped-feet` case, on real pipeline output:
    take a real clip whose feet ARE visible, blank the detector's ankle
    keypoints the way a knees-up framing would, and check the floor disappears
    rather than surviving on the reconstruction's own (always-present,
    always-confident) foot joints."""
    names = [j["name"] for j in json.loads((HERE / "mhr_joint_hierarchy.json").read_text())["joints"]]
    data = np.load(REAL_NPZ, allow_pickle=True)
    detections = [
        {
            "track_ids": d["track_ids"],
            "boxes": d["boxes"],
            "keypoints": _blank_ankles(d["keypoints"]),
        }
        for d in data["raw_detections"]
    ]
    tracks = g.foot_tracks_from_clip(
        data["per_frame"], detections, data["confident_track_ids"].tolist(), names
    )
    result = g.solve_grounding(tracks, data["sample_times_s"])
    assert result.grounding["status"] == "none"
    assert result.grounding["floor_plane"] is None
    assert result.diagnostics["reason"] == "feet_not_visible_enough"
    assert result.diagnostics["foot_visible_fraction"] == 0.0


def _blank_ankles(keypoints):
    kp = np.array(keypoints, dtype=np.float64, copy=True)
    if kp.size:
        kp[:, [g.COCO_ANKLE["left"], g.COCO_ANKLE["right"]], 2] = 0.0
    return kp
