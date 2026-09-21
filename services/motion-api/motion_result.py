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
modal_app adds both files to the glTF image so the worker sees them too.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

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


def _rest_relative_rotation(rest_xyzw, skel_xyzw):
    """JointHierarchy.rotation_convention: identity == exactly the rest pose.
    skel_state's rotation (verified against a real run, see report) is the
    ABSOLUTE local-to-parent rotation, not already rest-relative -- so the
    contract value is rest_rotation^-1 * skel_rotation."""
    return _quat_mul(_quat_conj(rest_xyzw), skel_xyzw)


def build_motion_result(job_id: str, clip_id: str, npz_bytes: bytes,
                        manifest: dict | None, perf: dict | None) -> dict:
    """Pure: every input is passed in, nothing is read from a Volume here."""
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
    root_idx = JOINT_HIERARCHY["root_joint_index"]

    persons = []
    for pi, track_id in enumerate(data["confident_track_ids"].tolist()):
        held = None  # most recent observed skel_state (127, 8) for this track
        samples_out = []
        root_traj = []
        n_observed = 0
        shape_fitted = False  # did ANY frame fit this dancer's shape?

        for i in range(n_samples):
            frame = per_frame[i]
            person = frame.get(track_id) if isinstance(frame, dict) else None
            observed = person is not None and "skel_state" in person
            if observed:
                held = np.asarray(person["skel_state"], dtype=np.float64)
                n_observed += 1
                # Only whether a fit happened is kept, never the fitted vector
                # itself -- see the ShapeParams block below.
                shape_fitted = shape_fitted or "shape_params" in person

            if held is None:
                # Leading gap: never reconstructed yet at all for this track.
                joints_sample = [
                    {"rotation": [0, 0, 0, 1], "provenance": {"observed": False, "interpolated": False, "suppressed": "out_of_frame"}, "visibility": "absent"}
                    for _ in range(n_joints)
                ]
                root_traj.append({
                    "position": [0.0, 0.0, 0.0],
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
                joints_sample = []
                for ji in range(n_joints):
                    skel_xyzw = tuple(float(v) for v in held[ji, 3:7])
                    rel = _rest_relative_rotation(rest_rotations[ji], skel_xyzw)
                    joints_sample.append({
                        "rotation": list(rel),
                        "provenance": provenance,
                        "visibility": visibility,
                    })
                root_pos_cm = held[root_idx, 0:3]
                root_traj.append({
                    # cm -> meters, same scale factor verified against
                    # joint_hierarchy.rest_translation (see dump_joint_hierarchy).
                    # ponytail: this is skel_state's own (character-local)
                    # frame, NOT composed with camera extrinsics/pred_cam_t
                    # into true world space -- see report's open item on
                    # root-trajectory world placement.
                    "position": [float(root_pos_cm[0]) / 100.0, float(root_pos_cm[1]) / 100.0, float(root_pos_cm[2]) / 100.0],
                    "rotation": list(tuple(float(v) for v in held[root_idx, 3:7])),
                    "provenance": provenance,
                })

            samples_out.append({"joints": joints_sample})

        glb_name = manifest["glb_paths"].get(str(track_id))
        persons.append({
            "person_id": f"person_{track_id}",
            "track_id": int(track_id),
            "animation": {"clip_id": f"{clip_id}_track{track_id}", "glb_asset_id": glb_name},
            # `vector` is deliberately NOT served. It is 45 floats describing
            # this specific person's body proportions -- the most person-specific
            # number the system produces -- and it was being broadcast to every
            # browser that opened a lesson while no client read it. Verified
            # across every branch that has viewer code (apps/web on w5-viewer,
            # packages/navigation on w11-beats): the only references anywhere
            # are the schema, the generated types and the fixtures. What the
            # viewer actually needs is `source`, which drives the honesty
            # labelling ("do not present body proportions as measured").
            #
            # The vector still exists server-side and is still needed there --
            # the shape-params branch bakes it into the exported mesh -- so
            # this removes it from the payload, not from the pipeline.
            #
            # Schema note: `vector` is `required` in motion-result.schema.json,
            # so this document does not validate against the frozen v1.0.0
            # contract until ShapeParams drops it from `required`. That is a
            # minor-version bump and a fixture regeneration, owned by whoever
            # holds the contract -- see the report and OPEN-DECISIONS D7.
            "shape_params": {
                "source": "well_observed_frames" if shape_fitted else "default_assumed",
            },
            "root_trajectory": root_traj,
            "samples": samples_out,
            "crop_rects": {"hands": [None] * n_samples, "feet": [None] * n_samples},  # Milestone B, not built here
        })

    width = int(data["frame_width"]) if "frame_width" in data else 0
    height = int(data["frame_height"]) if "frame_height" in data else 0
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
            # ponytail: NOT a real calibration -- Milestone A hasn't built
            # camera-intrinsics estimation. A plausible-looking but unverified
            # focal length would be a confidently-wrong claim (DESIGN.md §7h),
            # so this is deliberately a naive, clearly-placeholder guess
            # (fx=fy=max(w,h), centered principal point), not a measurement.
            "intrinsics": {
                "fx": float(max(width, height, 1)),
                "fy": float(max(width, height, 1)),
                "cx": width / 2.0,
                "cy": height / 2.0,
                "reference_width_px": width or 1,
                "reference_height_px": height or 1,
            },
            "camera_to_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        },
        # Never fake a plane (DESIGN.md §10) -- floor fitting isn't built yet,
        # so "none" is the honest state, not a guessed floor at y=0.
        "grounding": {"status": "none", "floor_plane": None},
        "accent_color": {"hex": DANCER_FALLBACK_COLORS[0], "source": "fallback"},  # E4 sampling not built here
        "joint_hierarchy": JOINT_HIERARCHY,
        "persons": persons,
        "model_report": {
            "pipeline_git_sha": "808b53c",
            "models": [
                {"name": "rtmo-m", "version": "body7", "license": "Apache-2.0", "license_flags": []},
                {"name": "bytetrack", "version": "upstream-main", "license": "MIT", "license_flags": []},
                {"name": "sam-3d-body-dinov3", "version": "hf:facebook/sam-3d-body-dinov3", "license": "SAM License",
                 "license_flags": ["itar-military-use-prohibited", "citation-required-for-research-publication"]},
                {"name": "mhr", "version": "v1.0.1", "license": "Apache-2.0", "license_flags": ["body-model-asset-license-see-zip"]},
            ],
            "measured_performance": perf,
        },
    }
    return doc
