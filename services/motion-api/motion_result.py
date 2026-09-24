"""Assemble a `MotionResult` contract document from the pipeline's npz.

Lifted verbatim out of api.py (W4) so it can run in TWO places, because that
is what lets the 61.30 MB npz be deleted:

  * `modal_app.export_clip_gltf` calls it ONCE, on the GPU worker, right after
    the GLBs are written, and stores the result. Then it deletes the npz.
  * `api.py` calls it only as a fallback, for lessons reconstructed before the
    materialisation existed and which therefore still have an npz and no
    stored document.

Nothing about the assembly changed in the move except that failures raise
`MotionResultUnavailable` instead of fastapi's `HTTPException` -- this module
must import cleanly in the glTF container, which has numpy and pymomentum and
no web framework at all. api.py translates the exception back to the same HTTP
statuses it raised before.

`JOINT_HIERARCHY` is read from `mhr_joint_hierarchy.json` next to this file;
modal_app adds all three files (this one, the hierarchy, and grounding.py) to
the glTF image so the worker sees them too.

INTEGRATION NOTE (second pass, docs/INTEGRATION.md §2). "Lifted verbatim out
of api.py" was true of `api.py` **as it stood on `w4-jobservice`**, which is
where this branch was cut. By the time the move landed, four other packages
had already changed the very function being moved, and a verbatim lift
silently reverted all four with no conflict and no failing test:

  * `export-quality`  -- the world-vs-local rotation fix (`_local_rotations`).
    Without it every joint below the root is served its whole chain's
    accumulated orientation, a measured median of 125.7 degrees wrong.
  * `grounding`       -- the real floor solve, replaced by a hardcoded
    `{"status": "none"}`, and the real camera intrinsics, replaced by the
    fx=fy=max(w,h) placeholder (12.8% low on solo-01).
  * `hands`           -- the per-frame crop rects, replaced by `[None] * n`.
  * `world-placement` -- the corrected root_trajectory rationale.

This module now carries the MERGED builder, not the w4-era one. The two things
the move genuinely intended -- the pure signature/`MotionResultUnavailable`,
and `shape_params.vector` no longer leaving the server -- are preserved and
marked at their sites.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

# Pure numpy, no web framework and no torch, so it imports fine in the glTF
# container as well as the API container. modal_app mounts it alongside this
# file for exactly that reason.
from grounding import camera_intrinsics_from_clip, solve_grounding_camera_space
# world_placement_probe.place_track is the measured world-placement solve
# (docs/research/world-placement.md, OPEN-DECISIONS E6): rigid skeleton +
# per-frame 3-DoF PnP against the detector's own keypoints + a 5-frame median
# filter. Imported, not re-implemented -- see the INTEGRATION NOTE below for
# why a "verbatim lift" of this exact logic has already gone wrong once.
# modal_app mounts it (and skeleton_constraints.py, which it needs) alongside
# grounding.py and this file for the same reason.
import world_placement_probe as wp
# hand_crops lives in vendor/fast-sam-3d-body/tools, which world_placement_probe
# has just put on sys.path (and which both Modal images mount, next to
# skeleton_constraints -- see modal_app.py). Pure numpy.
import hand_crops as hc  # noqa: E402

JOINT_HIERARCHY = json.loads(
    (Path(__file__).resolve().parent / "mhr_joint_hierarchy.json").read_text()
)
DANCER_FALLBACK_COLORS = ["#E8952F", "#1E7A6F", "#C2417E", "#3F51B5"]  # DESIGN.md section 3


class MotionResultUnavailable(Exception):
    """No MotionResult can be assembled, with the HTTP status api.py should use."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_conj(q):
    x, y, z, w = q
    return (-x, -y, -z, w)


def _rest_relative_rotation(rest_xyzw, local_xyzw):
    """JointHierarchy.rotation_convention: identity == exactly the rest pose.
    Given a joint's PARENT-RELATIVE rotation, the contract value is
    rest_rotation^-1 * local_rotation. See _local_rotations for why the
    caller has to compute that parent-relative rotation first."""
    return _quat_mul(_quat_conj(rest_xyzw), local_xyzw)


def _local_rotations(skel_state, parents):
    """skel_state quaternions are WORLD rotations -- convert to parent-relative.

    This was the bug. skel_state's rotation was being fed straight into
    _rest_relative_rotation as though it were already local-to-parent, so every
    joint below the root was served the *accumulated* orientation of its whole
    chain instead of its own bend. Measured on the real solo-01 reconstruction
    (291 frames, 127 joints) the two differ by a median of 125.7 degrees, p90
    168.2, and 125 of 127 joints are off by more than 20 degrees on average --
    this was not a subtle sign error, the served skeleton was wrong everywhere
    below the pelvis.

    Confirmed from the data rather than from the format docs, two ways. A rig's
    bone offset -- a child's position expressed in its parent's frame -- is a
    property of the skeleton, so it must not move as the dancer moves. Treating
    the quaternions as WORLD makes it rigid; treating them as parent-relative
    does not:

        offset vector wander / bone length   q as WORLD   q as parent-relative
          median                               0.000574              0.949570
        |mean offset - rest_translation|, m
          median                               0.004111              0.048569

    That second row is checked against joint_hierarchy's own rest_translation,
    dumped independently from the FBX skeleton, which neither hypothesis can
    tune itself against. Corroborating: skel_state[:, :3] are plainly absolute
    world positions -- c_head_null sits 1.678 m from the origin, which no local
    bone offset could be.

    Matches `decompose()` on branch `smoothing`, which independently reached
    the same conclusion (its decompose/recompose round-trips to 5.7e-14 cm).
    Scale is deliberately ignored here: it cancels in a pure rotation.
    """
    out = [None] * len(parents)
    for ji, parent in enumerate(parents):
        world = tuple(float(v) for v in skel_state[ji, 3:7])
        if parent < 0:
            out[ji] = world  # root: its parent IS the world, so local == world
        else:
            parent_world = tuple(float(v) for v in skel_state[parent, 3:7])
            out[ji] = _quat_mul(_quat_conj(parent_world), world)
    return out


def _proposed_counts(beats: dict | None, sample_times_s: list) -> dict | None:
    """Shape `beat_detect.propose_grid()`'s output into the contract's
    `proposed_counts`, or None.

    `count_total` is RE-DERIVED here against `sample_times_s[-1]`, never taken
    from the beat module. The beat module only ever saw ffprobe's container
    duration, which is not the same number as the last sample slot -- and the
    contract's invariant (and `normalizeStructure`, which renders this) is
    stated against the sample timeline. A grid one count longer than the dance
    is the kind of disagreement nothing else in the document would notice.
    """
    if not beats or not sample_times_s:
        return None
    spc = float(beats["seconds_per_count"])
    if not spc > 0:
        return None
    count_one_s = max(0.0, float(beats["count_one_s"]))
    end_s = float(sample_times_s[-1])
    ones = [
        {"count_one_s": float(a["count_one_s"]), "shift_counts": int(a["shift_counts"]), "confidence": float(a["confidence"])}
        for a in beats.get("count_one_alternates", [])
        if 0 <= float(a["count_one_s"]) <= end_s
    ][:3]
    return {
        "count_one_s": count_one_s,
        "seconds_per_count": spc,
        "count_total": max(1, int((end_s - count_one_s) // spc) + 1),
        "confidence": float(beats["confidence"]),
        "bpm": float(beats["bpm"]),
        "alternates": [
            {"label": a["label"], "seconds_per_count": float(a["seconds_per_count"]), "bpm": float(a["bpm"])}
            for a in beats.get("alternates", [])
        ],
        "warnings": list(beats.get("warnings", [])),
        **({"count_one_alternates": ones} if ones else {}),
    }


def build_motion_result(job_id: str, clip_id: str, npz_bytes: bytes | None,
                        manifest: dict | None, perf: dict | None,
                        beats: dict | None = None) -> dict:
    """Pure: every input is passed in, nothing is read from a Volume here.

    `beats` is `beat_detect.propose_grid()`'s output as a dict, or None. None is
    a normal outcome (no audio track, silent clip, the beat stage failed or was
    never run) and must not fail the job -- the learner sets counts by hand,
    which they can always do anyway. Defaulted rather than required so the two
    existing call sites and every stored npz keep working unchanged.
    """
    import numpy as np

    if npz_bytes is None:
        raise MotionResultUnavailable(404, "No pipeline output for this job yet.")
    data = np.load(io.BytesIO(npz_bytes), allow_pickle=True)
    if bool(data["refused"]):
        raise MotionResultUnavailable(409, "This job was refused; there is no MotionResult to serve.")
    if manifest is None:
        raise MotionResultUnavailable(409, "Reconstruction finished but the GLB export manifest is missing.")

    sample_times_s = data["sample_times_s"].tolist()
    per_frame = data["per_frame"]
    n_samples = len(per_frame)
    joints_def = JOINT_HIERARCHY["joints"]
    n_joints = len(joints_def)
    rest_rotations = [tuple(j["rest_rotation"]) for j in joints_def]
    parents = [j["parent_index"] for j in joints_def]
    root_idx = JOINT_HIERARCHY["root_joint_index"]

    confident_track_ids = data["confident_track_ids"].tolist()

    # World-placement solve, once per confidently-tracked dancer. None means
    # "not placed" -- fewer than 25 frames (world_placement_probe's own
    # minimum-evidence gate) or the npz predates frame_width/frame_height
    # (place_track requires them; older lessons rebuilt through api.py's
    # fallback path do not have them). Either way the dancer still gets a
    # best-effort root_trajectory below, from skel_state alone, exactly as
    # before this change.
    placements: dict[int, dict | None] = {}
    for track_id in confident_track_ids:
        try:
            placements[track_id] = wp.place_track(data, track_id)
        except Exception as e:  # noqa: BLE001
            print(f"[world-placement] {clip_id} track {track_id}: not placed ({e})")
            placements[track_id] = None

    width = int(data["frame_width"]) if "frame_width" in data else 0
    height = int(data["frame_height"]) if "frame_height" in data else 0
    raw_detections = data["raw_detections"] if "raw_detections" in data else []

    persons = []
    for pi, track_id in enumerate(confident_track_ids):
        held = None  # most recent observed skel_state (127, 8) for this track
        samples_out = []
        root_traj = []
        n_observed = 0
        shape_vec = None

        # Composed world position per sample index, contract world space
        # (metres, Y-up) -- see world-placement.md and the CORRECTION comment
        # below. Built once per track: place_track's rows only cover frames
        # where the track was actually seen by both the reconstruction and
        # the detector, and its own 5-frame median filter can still leave a
        # row NaN (long correspondence gaps), so this is a sparse map, held
        # forward across gaps exactly like `held` (skel_state) is below.
        placement = placements.get(track_id)
        composed_position = {}
        if placement is not None:
            world_pts = (placement["joints"][:, root_idx, :] + placement["trans"]) * np.array([1.0, -1.0, -1.0])
            valid_rows = np.isfinite(world_pts).all(axis=1)
            for k, i in enumerate(placement["idx"]):
                if valid_rows[k]:
                    composed_position[int(i)] = world_pts[k]
        # Seeded with the FIRST solved position rather than None, i.e. the
        # leading gap is BACK-FILLED -- the same argument, and the same fix,
        # modal_app.export_clip_gltf already applies to skel_state's leading
        # gap.  A track can be reconstructed on a sample whose placement did
        # not solve (solo-01's first sample is one of its 4 NaN translation
        # rows), and leaving those on the pinned constant put the dancer at
        # the old character-local origin for one frame and then TELEPORTED
        # them 6.14 m -- measured; solo-07 track 3 jumped 7.73 m.  A held
        # pose reads as a freeze, which is honest; a 6 m jump reads as real
        # travel, which is a lie about what the pipeline saw.
        placed = bool(composed_position)
        held_position = composed_position[min(composed_position)] if placed else None
        # branch `hands`: crop rects are computed in the GPU stage (they need the
        # detector keypoints and the real post-rotation frame size, both of which
        # only exist there) and carried per-person in the npz, same as
        # bone_length_confidence. Here they are only collected, never invented --
        # a frame the pipeline did not localize stays None.
        hand_rects, foot_rects = [], []

        for i in range(n_samples):
            frame = per_frame[i]
            person = frame.get(track_id) if isinstance(frame, dict) else None
            observed = person is not None and "skel_state" in person
            hand_rects.append(person.get("hand_crop_rect") if person is not None else None)
            foot_rects.append(person.get("foot_crop_rect") if person is not None else None)
            if observed:
                held = np.asarray(person["skel_state"], dtype=np.float64)
                n_observed += 1
                if shape_vec is None:
                    # Fallback only, for GLBs exported before the shape bake: one
                    # frame's estimate, which is a noisy sample of the body rather
                    # than the clip-wide fit ShapeParams.source promises.
                    shape_vec = person["shape_params"].tolist()
            if i in composed_position:
                held_position = composed_position[i]

            if held is None:
                # Leading gap: never reconstructed yet at all for this track.
                joints_sample = [
                    {"rotation": [0, 0, 0, 1], "provenance": {"observed": False, "interpolated": False, "suppressed": "out_of_frame"}, "visibility": "absent"}
                    for _ in range(n_joints)
                ]
                root_traj.append({
                    # Back-filled from this track's first solved placement, not
                    # the origin.  The contract is explicit that a position on a
                    # suppressed sample is not a claim, and `out_of_frame` +
                    # `absent` joints say plainly that nobody was there yet --
                    # but the origin STOPPED being a neutral placeholder the
                    # moment world space became the camera's.  It is now a real
                    # spot in the room, inside the camera, metres from the
                    # dancer, and a consumer that reads position without first
                    # reading provenance gets a specific wrong answer instead of
                    # an obviously empty one.  apps/web's `travelExtent` is
                    # exactly that consumer: it ranges over every sample, so
                    # group-synced-01 track 5 -- 261 of its 496 samples are
                    # leading gap -- would have reported ~6.6 m of travel that
                    # is entirely this placeholder.  Holding the first real
                    # position is the same back-fill export_clip_gltf already
                    # does for skel_state, and it costs no honesty: the sample
                    # is still `out_of_frame`, still `absent`, still not
                    # `observed`.
                    "position": [float(v) for v in held_position] if held_position is not None else [0.0, 0.0, 0.0],
                    "rotation": [0, 0, 0, 1],
                    "provenance": {"observed": False, "interpolated": False, "suppressed": "out_of_frame"},
                })
            else:
                provenance = {"observed": observed, "interpolated": not observed, "suppressed": None if observed else "low_confidence"}
                # ponytail: every joint in a reconstructed frame gets the SAME
                # observed/uncertain state -- SAM 3D Body reconstructs a whole
                # body per frame, it doesn't classify per-joint occlusion.
                # Real per-joint visibility (which limb is actually occluded
                # this frame) is Milestone A's Kalman/suppression chain (W9),
                # not built here. Held (non-observed) frames render as
                # "uncertain", never "observed" or "absent" -- a frozen pose
                # is honestly disclosed, not claimed as tracked motion.
                visibility = "observed" if observed else "uncertain"
                # skel_state carries WORLD rotations; the contract wants each
                # joint's own bend relative to its parent. Convert once per
                # sample, not per joint -- see _local_rotations.
                local_rots = _local_rotations(held, parents)
                joints_sample = []
                for ji in range(n_joints):
                    rel = _rest_relative_rotation(rest_rotations[ji], local_rots[ji])
                    joints_sample.append({
                        "rotation": list(rel),
                        "provenance": provenance,
                        "visibility": visibility,
                    })
                root_pos_cm = held[root_idx, 0:3]
                if held_position is not None:
                    # WIRED (docs/research/world-placement.md, OPEN-DECISIONS
                    # E6): world_placement_probe.place_track's composed
                    # per-frame translation, converted into this same contract
                    # world space. `held` above is skel_state's own
                    # character-local frame, which on real clips is CONSTANT
                    # -- (0, 0.924, 0) on all 291 solo-01 frames -- because it
                    # never had the camera-space translation added in. This
                    # does: the dancer travels now instead of dancing in
                    # place. Forward-filled across any sample this track's
                    # placement could not solve (held_position only changes
                    # where `composed_position` has an entry for `i`), same as
                    # `held` (skel_state) is above -- a gap holds the last
                    # real placement rather than snapping back to the pinned
                    # constant.
                    #
                    # Falls back to the pinned constant only when this track
                    # was never placed at all (fewer than 25 frames, or an
                    # older npz missing frame_width/frame_height -- see
                    # `placements` above). Absolute metric scale is unverified
                    # beyond +/-10% and short/distant tracks are noisier
                    # (solo-07 track 3 measured 53 cm off) -- both still OPEN
                    # in OPEN-DECISIONS E6, not resolved by this wiring.
                    position = [float(v) for v in held_position]
                    # Placement is a per-sample claim of its own: a sample
                    # whose own translation solved is observed, one that
                    # inherited a held/back-filled position is not.  This is
                    # NOT the joint provenance above -- the pose can be
                    # observed on a sample whose placement was not.
                    root_prov = provenance if i in composed_position else {
                        "observed": False, "interpolated": True,
                        "suppressed": provenance["suppressed"] or "low_confidence",
                    }
                else:
                    # CORRECTION: the reason this was pinned was WRONG, not
                    # merely incomplete. It said composing pred_cam_t would
                    # "slide the dancer 7.75 m because they crouched". The
                    # source video says solo-01's dancer really does start
                    # ~10 m away and run toward the camera -- the 7.75 m is
                    # the choreography, and the -0.93 correlation with bbox
                    # height is the pinhole relation working, not an error.
                    position = [float(root_pos_cm[0]) / 100.0, float(root_pos_cm[1]) / 100.0, float(root_pos_cm[2]) / 100.0]
                    # This track was never placed (too few frames for
                    # world_placement_probe's 25-frame minimum -- solo-07
                    # tracks 5 and 9 have 21 and 14).  The pinned constant is
                    # NOT a world position in this document's world space: it
                    # sits 2.16 m above solo-07's own fitted floor, next to
                    # the camera.  A Vec3 is required here and there is no
                    # honest one, so the position stays the old placeholder
                    # and the provenance says so -- never `observed`, so a
                    # consumer that respects provenance (DESIGN.md 7h) does
                    # not draw this dancer standing in a spot nobody measured.
                    root_prov = {"observed": False, "interpolated": False,
                                 "suppressed": "low_confidence"}
                root_traj.append({
                    # cm -> meters, same scale factor verified against
                    # joint_hierarchy.rest_translation (see dump_joint_hierarchy).
                    "position": position,
                    # Unconverted on purpose, unlike the per-joint rotations
                    # above: the root has no parent, so its world rotation IS
                    # its local one, and the body's world orientation is
                    # exactly what root_trajectory is asking for.
                    "rotation": list(tuple(float(v) for v in held[root_idx, 3:7])),
                    "provenance": root_prov,
                })

            samples_out.append({"joints": joints_sample})

        # Report the vector the exporter actually baked into this dancer's GLB
        # (per-dim median over its observed frames) rather than a per-frame
        # sample, so the contract and the mesh cannot disagree.
        shape_vec = manifest.get("shape_params", {}).get(str(track_id), shape_vec)
        glb_name = manifest["glb_paths"].get(str(track_id))
        persons.append({
            "person_id": f"person_{track_id}",
            "track_id": int(track_id),
            "animation": {"clip_id": f"{clip_id}_track{track_id}", "glb_asset_id": glb_name},
            # `vector` is deliberately NOT served (branch `caching-retention`).
            # It is 45 floats describing this specific person's body
            # proportions -- the most person-specific number the system
            # produces -- and it was being broadcast to every browser that
            # opened a lesson while no client read it. Verified across every
            # branch with viewer code: the only references anywhere are the
            # schema, the generated types and the fixtures. What the viewer
            # actually needs is `source`, which drives the honesty labelling.
            # The vector still exists server-side and is still baked into the
            # exported mesh by `shape-params`; it just stops leaving the box.
            # `vector` was relaxed from required to optional in the frozen v1
            # schema in the same change, so this still validates.
            #
            # `source` is still decided by `shape_vec`, which prefers the
            # manifest's baked value over a per-frame sample -- so the label
            # keeps tracking what the exporter actually put in the GLB rather
            # than merely whether the npz happened to carry a shape key.
            "shape_params": {
                "source": "well_observed_frames" if shape_vec is not None else "default_assumed",
            },
            "root_trajectory": root_traj,
            "samples": samples_out,
            # Per-side crops are derived HERE, from the detector keypoints the
            # npz already stores, rather than in the GPU stage -- so any lesson
            # whose npz still exists gets them by rebuilding this document, no
            # re-reconstruction. Omitted (not all-null) when the npz predates
            # frame_width/frame_height: absent means "fall back to hands/feet".
            "crop_rects": {"hands": hand_rects, "feet": foot_rects,
                           **(hc.side_crop_rects(raw_detections, track_id, width, height)
                              if width and height else {})},
        })

    # One floor per clip, from every dancer's foot contacts pooled, in the
    # same camera space `placements` above solved translation in (real per-
    # frame depth, not the character-local frame's flattened one -- see
    # grounding.solve_grounding_camera_space). The diagnostics are
    # deliberately NOT put in the document (Grounding is
    # additionalProperties: false, and they are engineering numbers, not a
    # product claim) -- they go to the log so a "none" is explainable without
    # re-running the job.
    solved = solve_grounding_camera_space(
        [placements.get(tid) for tid in confident_track_ids], sample_times_s, n_samples,
    )
    grounding = solved.grounding
    print(f"[grounding] {clip_id}: {grounding['status']} -- {json.dumps(solved.diagnostics)}")
    intrinsics = camera_intrinsics_from_clip(data)
    proposed_counts = _proposed_counts(beats, sample_times_s)
    print(f"[beats] {clip_id}: " + (
        f"{proposed_counts['bpm']:.1f} BPM, {proposed_counts['count_total']} counts, "
        f"confidence {proposed_counts['confidence']:.2f}" if proposed_counts else "no proposal"))

    doc = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "source_video": {
            "asset_id": f"video:{clip_id}",
            "width_px": width or 1,
            "height_px": height or 1,
            "rotation_deg": 0,
            "duration_s": sample_times_s[-1] + (1.0 / (manifest.get("fps") or 15.0)) if sample_times_s else 1.0,
            "fps_nominal": manifest.get("fps", 15.0),
            "audio_offset_s": 0.0,
        },
        "sample_times_s": sample_times_s,
        "camera": {
            "model": "pinhole",
            # Real now, not the old fx=fy=max(w,h) placeholder: the pipeline's
            # own FOV estimate is in the npz per person (exactly constant per
            # clip), and the pinhole model it belongs to was verified by
            # reprojection at 0.00 px median error -- see
            # grounding.camera_intrinsics_from_clip. The placeholder was 12.8%
            # low on solo-01 (1024 vs 1174.88). Falls back to the placeholder
            # only for older npz files with no frame size recorded.
            "intrinsics": intrinsics or {
                "fx": float(max(width, height, 1)),
                "fy": float(max(width, height, 1)),
                "cx": width / 2.0,
                "cy": height / 2.0,
                "reference_width_px": width or 1,
                "reference_height_px": height or 1,
            },
            # WIRED (OPEN-DECISIONS E6). Still the identity -- but for the
            # opposite reason it used to be, and the same 16 numbers now mean
            # something completely different.
            #
            # BEFORE: a placeholder. World space was the GLB's character-local
            # frame, the body was pinned at the origin, and there was no camera
            # pose to write, so the identity stood in for "not placed yet".
            #
            # NOW: a measurement. World space IS the camera's own frame, and
            # camera_to_world is the camera's POSE IN THAT FRAME, which is by
            # construction the identity -- the camera sits at the world origin,
            # looking down -Z, which is the glTF convention this contract
            # mandates.
            #
            # The trap, and it was walked into once here: the
            # 180-degree-about-X flip (negate Y and Z) that
            # root_trajectory.position and grounding.floor_plane are built
            # through is NOT this matrix. That flip converts the probe's camera
            # convention (Y-down, Z-forward, positive depth) into the glTF
            # convention (Y-up, Z-backward); it is a change of basis applied to
            # the POINTS, already baked into every coordinate in this document.
            # Writing it here as well applies it a second time.
            #
            # Measured, because the two are indistinguishable by inspection.
            # apps/web/lib/motion.ts's projectToFrame is the one consumer; fed
            # 234 solo-01 ankle samples whose detector pixels place_track was
            # fitted against:
            #
            #   camera_to_world = identity        -> median 7.46 px, p90 22.75 px
            #   camera_to_world = diag(1, -1, -1) -> 234/234 behind the camera,
            #                                        projectToFrame returns null
            #
            # test_world_placement_wiring.py checks that round trip rather than
            # this literal, because the literal is exactly what was wrong.
            "camera_to_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        },
        # Real floor solve (grounding.py). Still returns "none" whenever the
        # evidence does not earn a plane -- DESIGN.md §10 forbids faking one,
        # and the solve's own diagnostics (logged above) say which gate
        # refused and what it measured.
        "grounding": grounding,
        "accent_color": {"hex": DANCER_FALLBACK_COLORS[0], "source": "fallback"},  # E4 sampling not built here
        "joint_hierarchy": JOINT_HIERARCHY,
        "persons": persons,
        "model_report": {
            "pipeline_git_sha": "808b53c",
            "models": [
                *([{"name": "librosa.beat_track", "version": "librosa>=0.10", "license": "ISC",
                    "license_flags": []}] if proposed_counts else []),
                {"name": "rtmo-m", "version": "body7", "license": "Apache-2.0", "license_flags": []},
                {"name": "bytetrack", "version": "upstream-main", "license": "MIT", "license_flags": []},
                {"name": "sam-3d-body-dinov3", "version": "hf:facebook/sam-3d-body-dinov3", "license": "SAM License",
                 "license_flags": ["itar-military-use-prohibited", "citation-required-for-research-publication"]},
                {"name": "mhr", "version": "v1.0.1", "license": "Apache-2.0", "license_flags": ["body-model-asset-license-see-zip"]},
            ],
            # performance.json also carries operator-only records (track_hygiene);
            # the contract object is closed, so only its three fields go out.
            "measured_performance": perf and {k: perf[k] for k in ("fps", "peak_vram_mb", "cost_usd")},
        },
    }
    # Optional by contract: omitted, never null, when there is no proposal.
    if proposed_counts:
        doc["proposed_counts"] = proposed_counts
    return doc
