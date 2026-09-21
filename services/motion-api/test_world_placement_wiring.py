"""The wiring test: does a real placement actually reach the document?

This file exists because the failure it guards against is SILENT.  Before this
wiring, `root_trajectory[].position` was skel_state's character-local root --
a per-clip CONSTANT, (0, 0.924, 0) on all 291 solo-01 frames -- so every
exported lesson had the dancer dancing in place while the source video shows
them running toward the camera.  Nothing crashed, nothing logged, the document
validated against the schema.  If `motion_result` ever stops composing
`world_placement_probe.place_track`'s translation (an import lost in a merge, a
swallowed exception, a refactor that drops the term), the output goes straight
back to that constant and nothing else in the test suite notices.

So: a synthetic clip whose dancer provably MOVES, driven through the real
`build_motion_result`, asserting the document says they moved.

    python3 -m pytest services/motion-api/test_world_placement_wiring.py -q
"""
import io

import numpy as np
import pytest

import motion_result as mr
import world_placement_probe as wp

N_JOINTS = 127
ROOT = mr.JOINT_HIERARCHY["root_joint_index"]
FOCAL, WIDTH, HEIGHT = 1174.8838, 576.0, 1024.0
PINNED_Y = 0.924  # the old constant, to the precision the bug showed it at


def _synth_npz(n_frames=60, track_ids=(1,), travel_m=4.0, short_track=None, fps=15.0):
    """A rigid body walking straight at the camera, rendered into an npz.

    The detector keypoints are the body's OWN reprojection under the clip's
    pinhole intrinsics, so the PnP in world_placement_probe has a correct
    answer to find and the test asserts against a KNOWN translation rather
    than against whatever the solver happens to produce.

    `short_track` is a track id given only 10 frames -- below place_track's
    25-frame minimum -- so the never-placed branch is exercised too.
    """
    rng = np.random.default_rng(0)
    # A body in camera space (metres, +Y DOWN), joints scattered around a
    # 1.7 m figure.  Constant across frames: this dancer is rigid, so every
    # bit of image-space change is the translation the solver must recover.
    body = rng.normal(0.0, 0.35, (N_JOINTS, 3))
    body[:, 1] = rng.uniform(-0.85, 0.85, N_JOINTS)
    body[ROOT] = (0.0, 0.0, 0.0)
    coco_rows = sorted(wp.COCO_TO_MHR)

    times = np.arange(n_frames) / fps
    per_frame, raw_detections = [], []
    truth = {}
    for i in range(n_frames):
        frame, ids, kps = {}, [], []
        for track_id in track_ids:
            if short_track is not None and track_id == short_track and i >= 10:
                continue
            # straight run toward the camera: depth shrinks, x drifts a little
            t = np.array([0.15 * i / n_frames, -0.9, 8.0 - travel_m * i / (n_frames - 1)])
            truth.setdefault(track_id, {})[i] = t
            placed = body + t
            uv = np.column_stack([
                FOCAL * placed[:, 0] / placed[:, 2] + WIDTH / 2.0,
                FOCAL * placed[:, 1] / placed[:, 2] + HEIGHT / 2.0,
            ])
            skel = np.zeros((N_JOINTS, 8), dtype=np.float32)
            skel[:, 0:3] = body * 100.0          # centimetres, character-local
            skel[ROOT, 0:3] = (0.0, PINNED_Y * 100.0, 0.0)   # the pinned constant, verbatim
            skel[:, 6] = 1.0                      # unit quaternion (w last)
            skel[:, 7] = 1.0                      # scale
            frame[track_id] = {
                "skel_state": skel,
                "shape_params": np.zeros(45, dtype=np.float32),
                "pred_joint_coords": body.astype(np.float64),
                "pred_cam_t": t.astype(np.float64),
                "focal_length": np.float32(FOCAL),
            }
            kp = np.zeros((17, 3), dtype=np.float64)
            for c in coco_rows:
                kp[c, :2] = uv[wp.COCO_TO_MHR[c]]
                kp[c, 2] = 0.95
            ids.append(track_id)
            kps.append(kp)
        per_frame.append(frame)
        raw_detections.append({"track_ids": np.asarray(ids), "keypoints": np.asarray(kps)})

    buf = io.BytesIO()
    np.savez(
        buf,
        refused=np.array(False),
        sample_times_s=times,
        per_frame=np.array(per_frame, dtype=object),
        raw_detections=np.array(raw_detections, dtype=object),
        confident_track_ids=np.asarray(track_ids),
        frame_width=np.array(int(WIDTH)),
        frame_height=np.array(int(HEIGHT)),
    )
    manifest = {"glb_paths": {str(t): f"synth_track{t}.glb" for t in track_ids}, "fps": fps}
    return buf.getvalue(), manifest, truth


def _positions(doc, person_index=0):
    return np.array([s["position"] for s in doc["persons"][person_index]["root_trajectory"]], dtype=float)


def _build(**kw):
    npz_bytes, manifest, truth = _synth_npz(**kw)
    return mr.build_motion_result("job_synth", "synth", npz_bytes, manifest, None), truth


# --------------------------------------------------------------------------- the guard

def test_the_dancer_travels_instead_of_dancing_in_place():
    """THE regression test.  A silent revert to the pinned constant fails here."""
    doc, _ = _build(travel_m=4.0)
    pos = _positions(doc)

    assert np.isfinite(pos).all()
    # the bug, stated as an assertion: every frame identical, y pinned at 0.924
    assert pos.std(axis=0).max() > 0.1, f"root_trajectory is constant: {pos[0]}"
    assert not np.allclose(pos[:, 1], PINNED_Y, atol=1e-3), "y reverted to the pinned constant"
    # and it travelled the distance the synthetic clip actually contains
    assert abs(np.ptp(pos[:, 2]) - 4.0) < 0.15, np.ptp(pos[:, 2])


def test_the_recovered_position_matches_the_known_translation():
    """Not just 'it moved' -- it moved to the right place, in contract world
    space (Y-up), which is the camera-space solve flipped about X."""
    doc, truth = _build(travel_m=4.0)
    pos = _positions(doc)
    want = np.array([truth[1][i] * np.array([1.0, -1.0, -1.0]) for i in sorted(truth[1])])
    err = np.linalg.norm(pos[: len(want)] - want, axis=1)
    assert np.median(err) < 0.05, f"median placement error {np.median(err):.3f} m"


def test_camera_to_world_is_not_the_identity_placeholder():
    """It was `identity` only for as long as the body was pinned at the origin.
    An identity here again means the two halves disagree about world space."""
    doc, _ = _build()
    assert doc["camera"]["camera_to_world"] == [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1]


def test_grounding_runs_on_the_camera_space_solve():
    """The old path fitted the floor in the character-local frame, where the
    feet never travel.  The tilt cap in the diagnostics is the cheapest proof
    of which solve ran, and it is logged, not invented, for every clip."""
    doc, _ = _build()
    solved = mr.solve_grounding_camera_space
    assert solved is not None
    # the camera-space cap, not MAX_TILT_DEG
    import grounding as g
    assert g.CAMERA_SPACE_MAX_TILT_DEG != g.MAX_TILT_DEG


def test_a_gap_holds_the_last_placement_and_never_snaps_back_to_the_pin():
    """A held position reads as a freeze; snapping to the pinned constant reads
    as a 6 m sprint.  Measured on the real clips before this was fixed:
    solo-01 teleported 6.14 m on its first sample, solo-07 track 3 7.73 m."""
    doc, _ = _build(travel_m=4.0)
    pos = _positions(doc)
    step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    # 4 m over 60 frames is ~7 cm/frame; anything near a metre is a snap-back
    assert step.max() < 0.5, f"discontinuity of {step.max():.2f} m in root_trajectory"


def test_an_unplaceable_track_is_never_reported_as_observed():
    """A track too short to place keeps the old pinned placeholder, because the
    contract requires a Vec3 and there is no honest one -- but it must not
    claim that placeholder as a measured world position.  In a clip whose floor
    is at y = -1.24 the pin sits 2.16 m up in mid-air (measured on solo-07,
    whose tracks 5 and 9 have 21 and 14 frames)."""
    doc, _ = _build(n_frames=60, track_ids=(1, 2), short_track=2)
    short = next(p for p in doc["persons"] if p["track_id"] == 2)
    pinned = [s for s in short["root_trajectory"]
              if s["provenance"]["suppressed"] != "out_of_frame"]
    assert pinned, "expected the short track to still appear in the document"
    assert all(abs(s["position"][1] - PINNED_Y) < 1e-3 for s in pinned)
    assert not any(s["provenance"]["observed"] for s in pinned), \
        "an unplaced track is claiming a measured world position"

    # ...while the long track in the same clip did get placed.
    long_track = next(p for p in doc["persons"] if p["track_id"] == 1)
    assert np.asarray([s["position"] for s in long_track["root_trajectory"]]).std(0).max() > 0.1

# --------------------------------------------------------------------------- honesty

def test_none_is_still_reachable_on_the_camera_space_path():
    """The wiring made `grounded` much EASIER to reach -- all three measured
    clips flipped from `none` to `grounded`.  That is only a good result if
    `none` is still the answer when the evidence is absent, so these are the
    three ways a real clip runs out of evidence, checked against the camera-
    space solve rather than the old character-local one.

    Guards the same property DESIGN.md 7h and evaluation/clips.yaml's
    `stress-cropped-feet` slot exist for: never fake a floor.
    """
    import copy

    import grounding as g

    npz_bytes, _, _ = _synth_npz(travel_m=4.0)
    data = np.load(io.BytesIO(npz_bytes), allow_pickle=True)
    n = len(data["per_frame"])
    times = np.asarray(data["sample_times_s"], dtype=float)
    placement = wp.place_track(data, 1)
    assert placement is not None

    assert g.solve_grounding_camera_space([placement], times, n).grounding["status"] == "grounded"

    # 1. the detector never sees the ankles (feet cropped out of the shot)
    blind = copy.deepcopy(placement)
    blind["visible"] = np.zeros_like(placement["visible"])
    assert g.solve_grounding_camera_space([blind], times, n).grounding["status"] == "none"

    # 2. nothing could be placed at all
    refused = g.solve_grounding_camera_space([None], times, n)
    assert refused.grounding["status"] == "none"
    assert refused.grounding["floor_plane"] is None
    # ...and the log says WHICH evidence ran out, not just that feet were not
    # visible -- there were no pooled tracks for feet to be visible in.
    assert refused.diagnostics["n_placements"] == 1
    assert refused.diagnostics["n_placed"] == 0
    assert refused.diagnostics["n_pooled"] == 0


def test_a_declined_track_is_counted_in_the_diagnostics():
    """solo-07 track 3 is the real case: placed, but short and 7-9 m out, and
    its own floor sits 53 cm off track 1's.  Pooling it moves the shared plane
    by 0.7 cm, so it is left in -- but whether a track was declined has to be
    visible in the log, or a `none` cannot be explained after the fact."""
    import grounding as g

    npz_bytes, _, _ = _synth_npz(travel_m=4.0)
    data = np.load(io.BytesIO(npz_bytes), allow_pickle=True)
    n = len(data["per_frame"])
    times = np.asarray(data["sample_times_s"], dtype=float)
    placement = wp.place_track(data, 1)

    d = g.solve_grounding_camera_space([placement, None], times, n).diagnostics
    assert (d["n_placements"], d["n_placed"], d["n_pooled"]) == (2, 1, 1)
