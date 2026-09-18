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


def _rest_relative_rotation(rest_xyzw, skel_xyzw):
    """JointHierarchy.rotation_convention: identity == exactly the rest pose.
    skel_state's rotation (verified against a real run, see report) is the
    ABSOLUTE local-to-parent rotation, not already rest-relative -- so the
    contract value is rest_rotation^-1 * skel_rotation."""
    return _quat_mul(_quat_conj(rest_xyzw), skel_xyzw)


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
