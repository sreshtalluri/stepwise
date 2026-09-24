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

Dedupe, retention and removal (this branch): every upload is perceptually
fingerprinted (fingerprint.py) and looked up in a content index
(retention.py). A clip that matches one already reconstructed reuses that
reconstruction instead of spending $0.06-0.08 of GPU on it again, and -- the
part that matters more -- a dancer who wants their reconstruction gone has one
canonical entry to remove rather than fifty scattered copies.

**Dedupe-on-upload only.** Every user still uploads their own clip; the only
thing skipped is the recompute. Nothing here lists, searches or exposes the
index, and nothing should: "storage at the direction of a user" and a
browsable catalogue of other people's dances are different products with
different legal postures (docs/research/rights-and-privacy.md §3d). The
technical distance between them is small enough that the restraint has to be
deliberate. See retention.py's own note.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import modal
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import fingerprint
import retention

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


def _volume_write_json(volume: modal.Volume, path: str, doc: dict) -> None:
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(doc))
    try:
        with volume.batch_upload(force=True) as batch:
            batch.put_file(str(tmp), path)
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# POST /clips -- upload, store, dispatch. Returns immediately (spec item 2:
# .spawn(), never .remote()).
# ---------------------------------------------------------------------------

class DispatchResponse(BaseModel):
    clip_id: str
    job_id: str
    reused: bool = False


@app.post("/clips", response_model=DispatchResponse)
async def upload_clip(file: UploadFile = File(...)) -> DispatchResponse:
    job_clip_id = uuid.uuid4().hex
    job_id = f"job_{job_clip_id}"  # resumable: DESIGN.md §7c's copyable link is just this job_id

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
        try:
            fp_record = fingerprint.fingerprint(tmp_path)
        except Exception as exc:  # noqa: BLE001 -- unreadable video, not a dedupe problem
            raise HTTPException(400, "We could not read this video. Try a different file.") from exc

        idx = retention.index()
        # ponytail: linear scan of the index. See fingerprint.find_duplicate --
        # fine for the invite-only cohort, LSH banding when it is not.
        known = {cid: rec["fingerprint"] for cid, rec in idx.items() if rec.get("fingerprint")}
        match = fingerprint.find_duplicate(fp_record, known)

        if match is not None:
            record = idx.get(match)
            if record.get("removed_reason") == "takedown":
                # Stay-down. The fingerprint outlives the artifacts precisely so
                # that a removal cannot be undone by uploading the clip again.
                raise HTTPException(
                    451,
                    "Someone in this clip asked us to remove it, so we cannot make a lesson from it.",
                )
            if not record.get("removed_at"):
                record["job_ids"] = list(dict.fromkeys(record["job_ids"] + [job_id]))
                record["last_accessed"] = time.time()
                idx.put(match, record)
                # No bytes stored, no GPU spawned. The job points at the
                # canonical reconstruction; get_job_status mirrors its state.
                _volume_write_json(results_volume, f"/{job_id}.job-meta.json",
                                   {"clip_id": match, "canonical_job_id": record["job_ids"][0]})
                print(f"[dedupe] {job_id} reuses {match} (no GPU, no second copy of the video)")
                return DispatchResponse(clip_id=match, job_id=job_id, reused=True)
            # Expired: the record is a tombstone with no artifacts left. Fall
            # through and reconstruct under a fresh clip_id.

        with uploads_volume.batch_upload() as batch:
            batch.put_file(tmp_path, f"/{job_clip_id}.mp4")
    finally:
        os.unlink(tmp_path)

    idx.put(job_clip_id, retention.new_record(job_clip_id, fp_record, job_id))
    # job_id -> clip_id is needed later (retry, result-building) without
    # parsing it back out of the job_id string -- write it once, here.
    _volume_write_json(results_volume, f"/{job_id}.job-meta.json", {"clip_id": job_clip_id})

    _run_clip_fn().spawn(clip_id=job_clip_id, job_id=job_id)
    return DispatchResponse(clip_id=job_clip_id, job_id=job_id, reused=False)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} -- the polling endpoint W7's ProcessingScreen/lib/jobStatus.ts
# needs. Reads the real job-status.schema.json document run_clip wrote to the
# results Volume, unmodified (no reinterpretation, spec item 5).
# ---------------------------------------------------------------------------

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    doc = _volume_read_json(results_volume, f"/{job_id}.job-status.json")
    if doc is None:
        # Removed is checked before "not written yet", because purge_clip
        # deletes the job-status file: without this branch a taken-down lesson
        # would poll as `queued` forever, which is a false statement about our
        # own data (DESIGN.md §7h applies to plumbing, not just copy).
        marker = retention.removal_marker(results_volume, job_id)
        if marker is not None:
            raise HTTPException(410, "This lesson was removed, and the link no longer works.")

        # A deduped job never runs its own reconstruction -- it mirrors the
        # canonical job's status under its own job_id, so the client's polling
        # contract is unchanged and the share link stays the caller's own.
        meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
        canonical = (meta or {}).get("canonical_job_id")
        if canonical and canonical != job_id:
            mirrored = dict(get_job_status(canonical))
            mirrored["job_id"] = job_id
            return mirrored

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

        for i in range(n_samples):
            frame = per_frame[i]
            person = frame.get(track_id) if isinstance(frame, dict) else None
            observed = person is not None and "skel_state" in person
            if observed:
                held = np.asarray(person["skel_state"], dtype=np.float64)
                n_observed += 1

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
            # The 45-dim MHR shape vector is the most person-specific number in
            # the system (body proportions), it was broadcast to every browser
            # that opened a lesson, and nothing consumed it -- the rendered mesh
            # is the stock lod3.fbx character driven by pose, not a fitted body
            # (docs/research/rights-and-privacy.md §2, §6.2). It is now neither
            # persisted (tools/process_clip.py's keep-set) nor served: the
            # server genuinely does not hold it any more, so this vector is the
            # MHR default and saying so is the truth, not a redaction.
            #
            # `source` keeps its real meaning -- whether this track was ever
            # observed well enough to fit a shape at all -- which is the honesty
            # signal the field exists for, and is exactly what the old
            # `shape_vec is not None` test computed.
            #
            # OPEN: motion-result.schema.json marks `vector` required with
            # minItems 1, so a constant zero vector is what keeps this
            # contract-valid without unilaterally bumping a frozen schema.
            # Dropping the field belongs in a 1.1.0 change made by whoever owns
            # the contract -- see the report and OPEN-DECISIONS D6/D7.
            "shape_params": {
                "vector": [0.0] * 45,
                "source": "well_observed_frames" if n_observed > 0 else "default_assumed",
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
    # Opening a lesson is what keeps it alive (retention.TTL_DAYS). A dance
    # people are still learning stays warm; a one-off ages out. Debounced to
    # one index write an hour -- see retention.touch.
    retention.touch(retention.index(), clip_id)
    return doc


# ---------------------------------------------------------------------------
# GET /assets/{asset_id} -- the "resolve separately at render time" endpoint
# both source_video.asset_id and AnimationRef.glb_asset_id require (schema
# comment: never a signed/expiring URL AS the id -- this endpoint is the
# separate resolution step, and streams bytes directly since there is no S3
# to presign against yet, see the storage-decision docstring above).
# ---------------------------------------------------------------------------

def _refuse_if_removed(clip_id: str) -> None:
    """A removed clip must stop serving bytes even if a file survived a partial
    purge. The index tombstone is the authority, not the filesystem."""
    record = retention.index().get(clip_id)
    if record is not None and record.get("removed_at"):
        raise HTTPException(410, "This lesson was removed, and the link no longer works.")


@app.get("/assets/{asset_id:path}")
def get_asset(asset_id: str) -> Response:
    if asset_id.startswith("video:"):
        clip_id = asset_id[len("video:"):]
        _refuse_if_removed(clip_id)
        video = _volume_read_bytes(uploads_volume, f"/{clip_id}.mp4") or _volume_read_bytes(eval_volume, f"/{clip_id}.mp4")
        if video is None:
            raise HTTPException(404, "No video for this asset id.")
        retention.touch(retention.index(), clip_id)
        return Response(content=video, media_type="video/mp4")
    if asset_id.endswith(".glb"):
        _refuse_if_removed(asset_id.split("_track")[0])
        glb = _volume_read_bytes(results_volume, f"/{asset_id}")
        if glb is None:
            raise HTTPException(404, "No GLB for this asset id.")
        return Response(content=glb, media_type="model/gltf-binary")
    raise HTTPException(404, "Unrecognized asset id.")


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/removal -- the takedown path. The highest-value item in
# docs/research/rights-and-privacy.md §6.1: the likely bad outcome is not a
# lawsuit, it is a dancer finding their own body reconstructed on a site they
# never heard of with no way to ask for it to stop.
#
# Keyed on job_id because that is what a lesson link actually contains
# (DESIGN.md §7c) -- the person asking has a link, not a clip_id, and will not
# have an account (D5 is open).
#
# **Removes first, asks later.** The alternative is a review queue with an
# acknowledged/removed/declined state machine; "declined" only exists if you
# hold the lesson up while you decide, and holding a dancer's reconstruction
# online while you deliberate is the thing being complained about. Removing
# immediately is both less code and a stronger promise, and it is what the
# recommended upload copy commits to ("anyone in a clip can ask us to take it
# down, and we will").
#
# The cost of that, stated rather than hidden: anyone holding a share link can
# delete that lesson, and restoring it needs the operator. That is the D5
# dependency §6.1 names, not something this endpoint can resolve alone. It is
# the cheaper failure -- a lesson wrongly removed can be re-uploaded by the
# person who made it; a reconstruction wrongly left up cannot be un-seen.
# ---------------------------------------------------------------------------

class RemovalRequest(BaseModel):
    reason: Optional[str] = None     # free text, kept only in the log
    contact: Optional[str] = None    # so the operator can reply; never stored in the index


class RemovalResponse(BaseModel):
    removed: bool
    clip_id: str
    links_disabled: int
    artifacts_deleted: int


@app.post("/jobs/{job_id}/removal", response_model=RemovalResponse)
def request_removal(job_id: str, body: Optional[RemovalRequest] = None) -> RemovalResponse:
    meta = _volume_read_json(results_volume, f"/{job_id}.job-meta.json")
    if meta is None:
        if retention.removal_marker(results_volume, job_id) is not None:
            raise HTTPException(410, "This lesson was already removed.")
        raise HTTPException(404, "Unknown lesson link.")
    clip_id = meta["clip_id"]

    # Deduping is what makes this genuinely better than chasing copies: every
    # job that resolved to this content is in one record, so one removal
    # disables all of their links at once.
    outcome = retention.purge_clip(
        clip_id, "takedown",
        uploads_volume=uploads_volume,
        results_volume=results_volume,
        extra_job_ids=[job_id],
    )
    print(f"[takedown] {clip_id} via {job_id}; reason={(body.reason if body else None)!r} "
          f"contact={(body.contact if body else None)!r}")
    return RemovalResponse(
        removed=True,
        clip_id=clip_id,
        links_disabled=len(outcome["job_ids"]),
        artifacts_deleted=len(outcome["files_deleted"]),
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True}
