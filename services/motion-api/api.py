"""W4: the HTTP layer between an uploaded clip and a real Modal GPU job.

Deliberately thin. This process never touches CUDA/torch/pymomentum -- it
only talks to Modal's control plane (spawn a Function, read/list a Volume)
and to disk for the upload's temp file, so it can run anywhere (a laptop, a
small always-on box) independent of the GPU image. The real pipeline lives in
modal_app.py + tools/process_clip.py; this file wires it to HTTP.

Object storage decision (see docs/PRD.md, docs/OPEN-DECISIONS.md E1 note on
GPU host): **Modal Volumes, not S3.** modal_app.py already uses three Volumes
(weights/eval-clips/results) as the only storage layer for everything the
pipeline reads and writes -- run_clip reads its input clip from a Volume path
and writes its job-status/npz/GLB output to one. Standing up S3/MinIO here
would mean two storage systems for one job (uploads in S3, everything
downstream in Modal Volumes) with a copy step between them for no benefit --
Volumes are already reachable from any process holding a Modal token (this
file proves it: no Modal container needed to read/write one), version data
with `.commit()`, and require zero new infrastructure or credentials beyond
what modal_app.py already needs. Cost: Volume reads go through Modal's client
library, not raw HTTP GET, so `/assets/{asset_id}` proxies bytes through this
service rather than redirecting to a public URL -- acceptable at this scale,
and swappable for real S3 + presigned URLs later without changing the
contract (asset_id stays opaque either way, see AnimationRef's schema
comment: never a signed/expiring URL AS the id itself).

Dispatch: modal.Function.lookup (this app must be `modal deploy`ed first,
see README) + .spawn() -- async, returns immediately. run_clip itself now
chains export_clip_gltf.remote() internally once reconstruction succeeds
(modal_app.py), so "dispatch run_clip, then export only if it succeeds" is
enforced inside the one spawned worker, not by this service polling and
re-dispatching.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import modal
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages" / "motion-contract" / "python"))
from motion_contract import validate_job_status, validate_motion_result  # noqa: E402

from grounding import camera_intrinsics_from_clip, solve_grounding_for_clip  # noqa: E402 -- same dir, pure numpy

APP_NAME = "stepwise-motion"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # generous; PRD's real limit is 60s of video, not a byte count
JOINT_HIERARCHY = json.loads((Path(__file__).resolve().parent / "mhr_joint_hierarchy.json").read_text())
DANCER_FALLBACK_COLORS = ["#E8952F", "#1E7A6F", "#C2417E", "#3F51B5"]  # DESIGN.md §3

uploads_volume = modal.Volume.from_name("stepwise-uploads", create_if_missing=True)
results_volume = modal.Volume.from_name("stepwise-results", create_if_missing=True)
eval_volume = modal.Volume.from_name("stepwise-eval", create_if_missing=True)

app = FastAPI(title="stepwise motion-api")


def _run_clip_fn():
    # Looked up per-call, not cached at import time: an app redeploy (new
    # code) should be picked up without restarting this service.
    return modal.Function.from_name(APP_NAME, "run_clip")


def _volume_read_json(volume: modal.Volume, path: str) -> Optional[dict]:
    try:
        buf = io.BytesIO()
        volume.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return json.loads(buf.getvalue())


def _volume_read_bytes(volume: modal.Volume, path: str) -> Optional[bytes]:
    try:
        buf = io.BytesIO()
        volume.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return buf.getvalue()


# ---------------------------------------------------------------------------
# POST /clips -- upload, store, dispatch. Returns immediately (spec item 2:
# .spawn(), never .remote()).
# ---------------------------------------------------------------------------

class DispatchResponse(BaseModel):
    clip_id: str
    job_id: str


@app.post("/clips", response_model=DispatchResponse)
async def upload_clip(file: UploadFile = File(...)) -> DispatchResponse:
    clip_id = uuid.uuid4().hex
    job_id = f"job_{clip_id}"  # resumable: DESIGN.md §7c's copyable link is just this job_id

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                os.unlink(tmp.name)
                raise HTTPException(413, "Clip is too large.")
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        with uploads_volume.batch_upload() as batch:
            batch.put_file(tmp_path, f"/{clip_id}.mp4")
    finally:
        os.unlink(tmp_path)

    # job_id -> clip_id is needed later (retry, result-building) without
    # parsing it back out of the job_id string -- write it once, here.
    meta_path = Path(tempfile.mkstemp(suffix=".json")[1])
    meta_path.write_text(json.dumps({"clip_id": clip_id}))
    try:
        with results_volume.batch_upload() as batch:
            batch.put_file(str(meta_path), f"/{job_id}.job-meta.json")
    finally:
        meta_path.unlink()

    _run_clip_fn().spawn(clip_id=clip_id, job_id=job_id)
    return DispatchResponse(clip_id=clip_id, job_id=job_id)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} -- the polling endpoint W7's ProcessingScreen/lib/jobStatus.ts
# needs. Reads the real job-status.schema.json document run_clip wrote to the
# results Volume, unmodified (no reinterpretation, spec item 5).
# ---------------------------------------------------------------------------

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    doc = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
    if doc is None:
        # Not a 404: a job that was just spawned and hasn't written its first
        # "queued" doc yet is a real, valid state, not a missing job. Distinct
        # from "job_id never existed" only by convention -- this service does
        # not keep its own job registry (the results Volume is the registry).
        return {
            "schema_version": "1.0.0",
            "job_id": job_id,
            "state": "queued",
            "stage_message": "",
            "progress": None,
            "error": None,
            "retry_count": 0,
        }
    result = validate_job_status(doc)
    if not result.valid:
        # Fail loudly, not silently -- serving a contract-invalid document is
        # worse than a 500 (DESIGN.md §7h's honesty rule applies to plumbing
        # too, not just copy).
        raise HTTPException(500, f"job-status document failed contract validation: {result.errors}")
    return doc


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/retry -- spec item 5: retryable is decided here, not
# auto-retried. A genuine pipeline/export crash (retryable=true) gets a
# manual retry button in the UI that calls this; "too_many_dancers"
# (retryable=false) has nothing this endpoint can do about it -- refused.
# Deliberately NOT automatic: auto-retrying a crash means silently spending
# GPU time on the same crash again with no backoff/circuit-breaker, which is
# out of scope to build correctly right now (see report).
# ---------------------------------------------------------------------------

@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    doc = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
    if doc is None:
        raise HTTPException(404, "Unknown job_id.")
    if doc["state"] != "failed":
        raise HTTPException(409, f"Job is '{doc['state']}', not 'failed' -- nothing to retry.")
    if not doc["error"] or not doc["error"]["retryable"]:
        raise HTTPException(409, "This failure is not retryable.")

    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    if meta is None:
        raise HTTPException(500, "No job-meta record for this job_id -- cannot recover its clip_id.")

    retry_count = doc["retry_count"] + 1
    _run_clip_fn().spawn(clip_id=meta["clip_id"], job_id=job_id, retry_count=retry_count)
    return {"job_id": job_id, "retry_count": retry_count}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/result -- build MotionResult from the real npz +
# export-manifest once the job has succeeded (spec item 4).
# ---------------------------------------------------------------------------

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


def _build_motion_result(job_id: str, clip_id: str) -> dict:
    import numpy as np

    npz_bytes = _volume_read_bytes(results_volume, f"/{clip_id}.npz")
    if npz_bytes is None:
        raise HTTPException(404, "No pipeline output for this job yet.")
    data = np.load(io.BytesIO(npz_bytes), allow_pickle=True)
    if bool(data["refused"]):
        raise HTTPException(409, "This job was refused; there is no MotionResult to serve.")

    manifest = _volume_read_json(results_volume, f"/{clip_id}.export-manifest.json")
    if manifest is None:
        raise HTTPException(409, "Reconstruction finished but the GLB export manifest is missing.")
    perf = _volume_read_json(results_volume, f"/{clip_id}.performance.json")

    sample_times_s = data["sample_times_s"].tolist()
    per_frame = data["per_frame"]
    n_samples = len(per_frame)
    joints_def = JOINT_HIERARCHY["joints"]
    n_joints = len(joints_def)
    rest_rotations = [tuple(j["rest_rotation"]) for j in joints_def]
    parents = [j["parent_index"] for j in joints_def]
    root_idx = JOINT_HIERARCHY["root_joint_index"]

    persons = []
    for pi, track_id in enumerate(data["confident_track_ids"].tolist()):
        held = None  # most recent observed skel_state (127, 8) for this track
        samples_out = []
        root_traj = []
        n_observed = 0
        shape_vec = None
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
                root_traj.append({
                    # cm -> meters, same scale factor verified against
                    # joint_hierarchy.rest_translation (see dump_joint_hierarchy).
                    #
                    # This is skel_state's own character-local frame, and on
                    # real clips it is CONSTANT -- (0, 0.924, 0) on all 291
                    # solo-01 frames -- so the dancer dances in place instead
                    # of travelling across the stage.
                    #
                    # CORRECTION (docs/research/world-placement.md): the reason
                    # previously recorded here was WRONG. It said composing
                    # pred_cam_t would "slide the dancer 7.75 m because they
                    # crouched". The source video says solo-01's dancer really
                    # does start ~10 m away and run toward the camera -- the
                    # 7.75 m is the choreography, and the -0.93 correlation
                    # with bbox height is the pinhole relation working. The
                    # independent PnP agreeing at r = 0.983 was confirmation,
                    # not a shared error.
                    #
                    # Still pinned here only because composing a per-frame
                    # translation changes what the export and the viewer mean
                    # by world space, which is OPEN-DECISIONS E6 and the
                    # builder's call. world-placement.md measures what the
                    # composed version buys (foot contacts on one floor: 52%
                    # -> 90%; five dancers agreeing on that floor to 5 cm
                    # instead of 37 cm) and services/motion-api/
                    # world_placement_probe.py reproduces it from an npz.
                    "position": [float(root_pos_cm[0]) / 100.0, float(root_pos_cm[1]) / 100.0, float(root_pos_cm[2]) / 100.0],
                    # Unconverted on purpose, unlike the per-joint rotations
                    # above: the root has no parent, so its world rotation IS
                    # its local one, and the body's world orientation is
                    # exactly what root_trajectory is asking for.
                    "rotation": list(tuple(float(v) for v in held[root_idx, 3:7])),
                    "provenance": provenance,
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
            "shape_params": {
                "vector": shape_vec if shape_vec is not None else [0.0] * 45,
                "source": "well_observed_frames" if shape_vec is not None else "default_assumed",
            },
            "root_trajectory": root_traj,
            "samples": samples_out,
            "crop_rects": {"hands": hand_rects, "feet": foot_rects},
        })

    width = int(data["frame_width"]) if "frame_width" in data else 0
    height = int(data["frame_height"]) if "frame_height" in data else 0

    # One floor per clip, from every dancer's foot contacts pooled. The
    # diagnostics are deliberately NOT put in the document (Grounding is
    # additionalProperties: false, and they are engineering numbers, not a
    # product claim) -- they go to the log so a "none" is explainable without
    # re-running the job.
    solved = solve_grounding_for_clip(data, [j["name"] for j in joints_def])
    grounding = solved.grounding
    print(f"[grounding] {clip_id}: {grounding['status']} -- {json.dumps(solved.diagnostics)}")
    intrinsics = camera_intrinsics_from_clip(data)

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
            # ponytail: identity, i.e. this document's "world space" IS the
            # exported GLB's own character-local frame -- which is what
            # root_trajectory and grounding.floor_plane are both expressed in,
            # so the document is self-consistent. It is NOT camera space, and
            # it cannot be until the dancer can be placed in the room at all
            # (OPEN-DECISIONS E6). Writing a real camera_to_world here while
            # the body is still pinned at the origin would make the document
            # internally inconsistent, not more truthful.
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


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str) -> dict:
    status = get_job_status(job_id)
    if status["state"] != "succeeded":
        raise HTTPException(409, f"Job is '{status['state']}', not 'succeeded'.")
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    clip_id = meta["clip_id"] if meta else job_id.removeprefix("job_")
    doc = _build_motion_result(job_id, clip_id)
    result = validate_motion_result(doc)
    if not result.valid:
        raise HTTPException(500, f"Assembled MotionResult failed contract validation: {result.errors}")
    return doc


# ---------------------------------------------------------------------------
# GET /assets/{asset_id} -- the "resolve separately at render time" endpoint
# both source_video.asset_id and AnimationRef.glb_asset_id require (schema
# comment: never a signed/expiring URL AS the id -- this endpoint is the
# separate resolution step, and streams bytes directly since there is no S3
# to presign against yet, see the storage-decision docstring above).
# ---------------------------------------------------------------------------

@app.get("/assets/{asset_id:path}")
def get_asset(asset_id: str) -> Response:
    if asset_id.startswith("video:"):
        clip_id = asset_id[len("video:"):]
        video = _volume_read_bytes(uploads_volume, f"/{clip_id}.mp4") or _volume_read_bytes(eval_volume, f"/{clip_id}.mp4")
        if video is None:
            raise HTTPException(404, "No video for this asset id.")
        return Response(content=video, media_type="video/mp4")
    if asset_id.endswith(".glb"):
        glb = _volume_read_bytes(results_volume, f"/{asset_id}")
        if glb is None:
            raise HTTPException(404, "No GLB for this asset id.")
        return Response(content=glb, media_type="model/gltf-binary")
    raise HTTPException(404, "Unrecognized asset id.")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
