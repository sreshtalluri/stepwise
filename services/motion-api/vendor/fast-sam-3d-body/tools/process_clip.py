# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Frame-by-frame clip pipeline: ffmpeg -> RTMO+ByteTrack -> SAM3DBodyEstimator.

Runs inside cv_image (Modal stage 5). Single-front-static camera. Per the
2026-09-18 scope revision (docs/PRD.md section 5), multiple dancers ARE in
the MVP: every confidently-tracked dancer gets full SAM 3D Body
reconstruction, up to a cap of MAX_DANCERS (W8: replaces the old
"violator-duet"/different-roles refusal rule, which predates this scope --
two dancers doing different things is now the normal case, evaluation/
clips.yaml's `violator-crowd` entry is the too-many-dancers refusal instead).
Cost is linear per dancer (no cross-dancer motion-correlation shortcut --
considered and rejected, see docs/GATE-REPORT.md's W8 addendum). What stays
out of scope here is cross-dancer consensus/identity-swap correction -- this
file hands back per-track data as-is, including through a track-id
discontinuity at a crossing; that is Milestone A+ (Kalman/suppression chain)
territory, not gate scope.

Output: one npz per clip with per-frame MHR parameters, keyed by the
normalized sample time (docs/PRD.md section 6: sample_times_s, not just a
frame index -- this is what makes gaps/re-entry representable at all), plus
the raw detector boxes/keypoints for the "raw detector overlays visible"
requirement in the week-one deliverable. Handed to the export stage as an
array file, not a live Python object -- that stage runs in a different
Python/torch version (see docs/PRD.md G3, E5).
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

# PRD §5's revised multi-dancer cap (docs/GATE-REPORT.md, W8 addendum): full
# reconstruction for every confidently-tracked dancer, refuse above this.
MAX_DANCERS = 6

# Floor for the one track tools/track_hygiene.py never drops (the clip's
# longest), so a clip with a dancer keeps one. Every other track has to clear
# track_hygiene's presence rules, which are far stricter than this.
CONFIDENT_MIN_FRAMES = 5

StageCallback = Optional[Callable[..., None]]
"""(stage, plain_language_message, progress_fraction_or_None, **milestones) -> None.
`milestones` is only passed by the reconstruction loop (frames_done,
frames_total), so a caller that shows only the message can ignore it.
Matches the plain-language, no-internal-jargon rule for job-status
stage_message (DESIGN.md §7c / job-status.schema.json) -- callers wire this to
whatever actually emits JobStatus documents (see modal_app.py::run_clip)."""


def _emit(on_progress: StageCallback, stage: str, message: str, progress: Optional[float],
          **milestones) -> None:
    if on_progress is not None:
        on_progress(stage, message, progress, **milestones)


def refusal_reason_for(n_confident_dancers: int, max_dancers: int = MAX_DANCERS) -> Optional[str]:
    """Returns a refusal reason code, or None if the clip should proceed."""
    return "too_many_dancers" if n_confident_dancers > max_dancers else None


def extract_frames(video_path: str, out_dir: str, fps: float = 15.0, max_seconds: float = 60.0) -> list[float]:
    """ffmpeg -> numbered JPEGs, and the exact sample time of each frame.

    fps is a *target*; ffmpeg's fps filter drops/duplicates to hit it, so the
    nominal `frame_index / fps` is not trustworthy on its own once VFR source
    footage is involved -- we still record the nominal times here (ffmpeg
    doesn't hand back per-frame real timestamps from the fps filter), but the
    field is named for what it is: the normalized-timeline schedule, not a
    measurement. Real dropped-frame detection needs comparing frame hashes or
    reading ffprobe's actual per-frame pts, which is out of scope for the gate.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"fps={fps}",
            "-t", str(max_seconds),
            "-q:v", "2",
            f"{out_dir}/frame_%06d.jpg",
        ],
        check=True,
        capture_output=True,
    )
    frame_files = sorted(Path(out_dir).glob("frame_*.jpg"))
    sample_times_s = [i / fps for i in range(len(frame_files))]
    return sample_times_s


def process_clip(
    video_path: str,
    checkpoint_path: str,
    mhr_path: str,
    frames_dir: str,
    fps: float = 15.0,
    max_seconds: float = 60.0,
    bbox_thr: float = 0.1,
    on_progress: StageCallback = None,
    on_detections: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Run the full detect+track+estimate pipeline over one clip.

    Two passes over the frames, not one:

    1. Detection-only pass (cheap: RTMO+ByteTrack, no SAM 3D Body). Decides
       which track ids are dancers (tools/track_hygiene.py: fragments of one
       body stitched into one id, blips and reflections dropped) and refuses
       the whole clip -- before spending any GPU
       time on reconstruction -- if that count exceeds MAX_DANCERS. This
       replaces the old "violator-duet"/different-roles refusal rule
       (docs/OPEN-DECISIONS.md doesn't cover this; the too-many-dancers cap
       is the new scope's own refusal condition per docs/GATE-REPORT.md's W8
       addendum, evaluation/clips.yaml's `violator-crowd`).
    2. Reconstruction pass: full SAM 3D Body reconstruction for every
       confidently-tracked dancer (docs/PRD.md section 5's multi-dancer MVP).
       A track that never became "confident" still gets its raw detection
       recorded (for the detector-overlay deliverable) but is not reconstructed
       -- cheap noise doesn't cost GPU time.

    Returns a dict of numpy arrays. per_frame[i] is a {track_id: person_dict}
    mapping (empty dict, not None, for frames with zero detections -- a
    suppressed/absent frame, not fabricated data; see docs/PRD.md section 4's
    observed/uncertain/absent states, which this does not itself implement --
    the gate proves the pipeline hands back genuinely-missing data instead of
    a fabricated pose, it does not implement the suppression/hysteresis logic
    that consumes it (that is Milestone A's own Kalman + suppression chain,
    not gate scope). track_id is ByteTrack's id after track_hygiene has
    stitched one body's fragments together (a re-detection near where the
    track was lost, or a duplicate box on the same body). Two dancers who
    CROSS can still swap ids -- no cross-dancer identity correction happens
    here, matching the multi-dancer scope revision's explicit non-goals
    (docs/PRD.md section 5).

    If the clip is refused (too many confidently-tracked dancers), returns a
    dict with `refused=True` and no reconstruction data -- callers must check
    this before treating the result as a normal MotionResult source.
    """
    import torch

    from sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
    from tools.build_detector import HumanDetector
    from tools.skeleton_constraints import constrain_clip  # branch: bone-constraints
    from tools.hand_crops import annotate_clip  # branch: hands
    from tools.track_hygiene import clean_tracks

    _emit(on_progress, "loading", "Loading the motion model", 0.0)
    device = torch.device("cuda")
    print(f"loading SAM 3D Body + MHR ({checkpoint_path}, {mhr_path})")
    model, model_cfg = load_sam_3d_body(checkpoint_path, device=device, mhr_path=mhr_path)

    # rtmlib's BaseTool does `'cuda' in device`, which requires a plain str
    # (a torch.device object isn't iterable) -- str(torch.device("cuda"))
    # gives exactly "cuda", so this is safe, not just a truncation.
    detector = HumanDetector(name="rtmo", device=str(device))
    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=model, model_cfg=model_cfg, human_detector=detector
    )

    _emit(on_progress, "extracting_frames", "Reading the video", 0.05)
    print(f"extracting frames from {video_path} at {fps} fps")
    sample_times_s = extract_frames(video_path, frames_dir, fps=fps, max_seconds=max_seconds)
    frame_files = sorted(Path(frames_dir).glob("frame_*.jpg"))
    print(f"{len(frame_files)} frames")

    # W4: MotionResult.source_video.width_px/height_px need the real
    # normalized frame size; cheapest correct source is the extracted frames
    # themselves (ffmpeg's fps filter is the only normalization applied so far
    # -- no resize/rotation yet, so this is also the source resolution).
    frame_height, frame_width = (0, 0)
    if frame_files:
        first_img = cv2.imread(str(frame_files[0]))
        if first_img is not None:
            frame_height, frame_width = first_img.shape[:2]

    # ---- Pass 1: detection only -- who's in this clip, and is it too many? ----
    _emit(on_progress, "detecting", "Finding the dancers in the clip", 0.1)
    raw_detections = []  # for the "raw detector overlays visible" deliverable
    for i, frame_path in enumerate(frame_files):
        img = cv2.imread(str(frame_path))
        det = detector.run_human_detection(img, bbox_thr=bbox_thr, default_to_full_image=False)
        raw_detections.append({
            "boxes": det["boxes"], "keypoints": det["keypoints"], "track_ids": det["track_ids"]
        })
        if i % 20 == 0:
            _emit(
                on_progress, "detecting",
                f"Finding the dancers in the clip, frame {i + 1} of {len(frame_files)}",
                0.1 + 0.15 * (i + 1) / max(1, len(frame_files)),
            )

    # Relabels stitched fragments in raw_detections in place, so pass 2, the
    # detections sidecar and the npz all see one id per body.
    dancer_ids, hygiene = clean_tracks(raw_detections, fps, min_frames=CONFIDENT_MIN_FRAMES)
    for d in hygiene:
        print(f"  track hygiene: {d}")
    confident_track_ids = set(dancer_ids)
    n_confident = len(confident_track_ids)
    print(f"{n_confident} dancer(s) after track hygiene: {sorted(confident_track_ids)}")

    if refusal_reason_for(n_confident) is not None:
        message = (
            f"This clip has {n_confident} dancers tracked confidently enough to "
            f"reconstruct, more than the {MAX_DANCERS} we can currently handle in one "
            "clip. Try a clip with fewer people, or trim to the part with the dancer "
            "you want to learn from."
        )
        _emit(on_progress, "refused", message, None)
        print(f"REFUSED: {message}")
        return {
            "refused": True,
            "refusal_reason": "too_many_dancers",
            "refusal_message": message,
            "n_confident_dancers": n_confident,
            "sample_times_s": np.array(sample_times_s, dtype=np.float64),
            "raw_detections": raw_detections,
            "frame_width": frame_width,
            "frame_height": frame_height,
        }

    # Pass 1's answer, handed out before the long pass starts, so the processing
    # screen can draw the detector's skeleton and say how many dancers it found.
    # A hook, not a return value: the caller decides where it goes.
    if on_detections is not None:
        on_detections({
            "sample_times_s": sample_times_s,
            "raw_detections": raw_detections,
            "confident_track_ids": sorted(confident_track_ids),
            "frame_width": frame_width,
            "frame_height": frame_height,
        })

    # ---- Pass 2: full reconstruction, confidently-tracked dancers only ----
    per_frame = []
    peak_vram_bytes = 0
    t_start = time.time()

    for i, (t_s, det) in enumerate(zip(sample_times_s, raw_detections)):
        boxes = det["boxes"]
        track_ids = det["track_ids"]
        keep = np.array([tid in confident_track_ids for tid in track_ids.tolist()], dtype=bool)
        boxes = boxes[keep]
        track_ids = track_ids[keep]

        if len(boxes) == 0:
            # Genuinely no confidently-tracked dancer this frame -- G5's gate:
            # no fabricated pose. Recorded as absent (empty dict), not silently
            # skipped, so the sample time still exists in the output (PRD
            # section 6).
            per_frame.append({})
            continue

        img = cv2.imread(str(frame_files[i]))
        # Every confidently-tracked dancer, not just one (docs/PRD.md section
        # 5, capped at MAX_DANCERS above). One process_one_image call, all
        # boxes at once -- SAM 3D Body runs per-crop internally, so this is N
        # crops in one batch, not N calls. Cost is linear in N, not free --
        # measure per-clip cost/fps here, don't assume it from the solo case.
        outputs = estimator.process_one_image(
            img,
            bboxes=boxes,
            bbox_thr=bbox_thr,
            hand_box_source="yolo_pose",
        )
        per_frame.append(dict(zip(track_ids.tolist(), outputs)))

        if torch.cuda.is_available():
            peak_vram_bytes = max(peak_vram_bytes, torch.cuda.max_memory_allocated())

        if i % 10 == 0:
            print(f"  frame {i}/{len(frame_files)}  t={t_s:.2f}s  "
                  f"dancers={len(boxes)}  vram_peak={peak_vram_bytes / 1e9:.2f}GB")
            _emit(
                on_progress, "reconstructing",
                f"Building the body, frame {i + 1} of {len(frame_files)}",
                0.25 + 0.7 * (i + 1) / max(1, len(frame_files)),
                frames_done=i + 1, frames_total=len(frame_files),
            )

    elapsed_s = time.time() - t_start
    n_ok = sum(1 for f in per_frame if f)
    print(
        f"done: {n_ok}/{len(per_frame)} frames reconstructed, "
        f"{elapsed_s:.1f}s total ({len(per_frame) / elapsed_s:.2f} fps), "
        f"peak VRAM {peak_vram_bytes / 1e9:.2f} GB"
    )
    _emit(on_progress, "reconstructing", "Finishing up", 0.95)

    # ---- bone-length constraint (branch `bone-constraints`) ----------------
    # Spatial, per-frame: gives every bone this dancer's own median length back
    # while keeping every bone's observed direction, and attaches a per-joint
    # confidence for the suppression stage. Must run before any temporal
    # smoothing. See tools/skeleton_constraints.py for the measured defect.
    bone_report = constrain_clip(per_frame, sorted(confident_track_ids))
    for tid, r in bone_report.items():
        print(f"  bone lengths, track {tid}: {r['n_bones']} bones fixed, worst frame off by "
              f"{r['worst_correction_factor']:.2f}x, {r['n_frames_with_uncertain_joint']}/"
              f"{r['n_frames']} frames carry an uncertain joint")
    # -----------------------------------------------------------------------

    # ---- hand/foot video crops + per-hand confidence (branch `hands`) -------
    # Runs after the bone constraint because it reads that stage's per-joint
    # `bone_length_confidence` at the wrist. Rects come from the detector's own
    # wrist/ankle keypoints and are normalized to [0,1] against the real
    # post-rotation frame size. See tools/hand_crops.py for why the answer to
    # "articulated 3D hands" is measured-no and the crop is the product.
    crop_report = annotate_clip(
        per_frame, raw_detections, sorted(confident_track_ids), frame_width, frame_height
    )
    for tid, r in crop_report.items():
        print(f"  crops, track {tid}: hands {r['n_hand_rects']}/{r['n_frames']} frames, "
              f"feet {r['n_foot_rects']}/{r['n_frames']} frames")
    # -----------------------------------------------------------------------

    # ---- W9 temporal smoothing + suppression (branch `smoothing`) ----------
    # INTEGRATION ORDER (docs/INTEGRATION.md): raw estimates -> bone-length
    # constraint (spatial) -> smoothing + suppression (temporal) -> export.
    # `smoothing` was cut from `w4-jobservice`, before the bone stage existed,
    # so its own insertion point was above the `done:` print and git merged it
    # there cleanly and silently -- i.e. temporal-before-spatial, which is the
    # wrong way round and which both branches' comments say must not happen.
    # Moved here at integration. It does not modify `per_frame`: the raw
    # estimates stay in the npz next to the smoothed ones, because a smoothed
    # value with honest flags is only checkable against the thing it smoothed.
    from tools.smoothing import repair_clip_orientation, smooth_clip_result

    # Front/back flips that last a frame or two (tools/smoothing.py,
    # "Orientation detours"). The one temporal fix that edits `per_frame`
    # itself, because the GLB export and the MotionResult both read the raw
    # skel_state from there; the estimate survives as `skel_state_raw`.
    flips = repair_clip_orientation({
        "per_frame": per_frame,
        "sample_times_s": np.array(sample_times_s, dtype=np.float64),
        "confident_track_ids": sorted(confident_track_ids),
    })
    for tid, idx in flips.items():
        if idx:
            print(f"  orientation flips, track {tid}: repaired samples {idx}")

    smoothed = smooth_clip_result({
        "per_frame": per_frame,
        "raw_detections": raw_detections,
        "sample_times_s": np.array(sample_times_s, dtype=np.float64),
        "confident_track_ids": sorted(confident_track_ids),
        "frame_width": frame_width,
        "frame_height": frame_height,
    })
    for tid, track in smoothed.items():
        s = track["stats"]
        print(f"  smoothing track {tid}: {s['n_samples_observed']} observed, "
              f"{s['n_samples_uncertain']} uncertain, {s['n_samples_absent']} absent "
              f"joint-samples ({s['n_samples_implausible']} physically impossible)")
    # -----------------------------------------------------------------------

    return {
        "refused": False,
        "track_hygiene": hygiene,  # stitched/dropped decisions, for the performance record
        "bone_length_report": bone_report,
        "crop_report": crop_report,
        "sample_times_s": np.array(sample_times_s, dtype=np.float64),
        "per_frame": per_frame,  # list of {track_id: person_dict}, one per sample time
        "smoothed": smoothed,  # W9: {track_id: smoothed skel_states + visibility/provenance}
        "raw_detections": raw_detections,
        "confident_track_ids": sorted(confident_track_ids),
        "faces": estimator.faces,
        "elapsed_s": elapsed_s,
        "peak_vram_bytes": peak_vram_bytes,
        "n_frames_ok": n_ok,
        "n_frames_total": len(per_frame),
        "frame_width": frame_width,
        "frame_height": frame_height,
    }


# Persisted by accident, read by nothing. save_clip_result used to pickle the
# estimator's whole per-person output dict, so every byproduct of one forward
# pass landed on disk forever.
#
# Measured on the real solo-01 npz (61.30 MB): `pred_vertices` is 57.90 MB of
# it -- 94.8% of the entire file -- at 18,439 x 3 floats per person per frame.
# Nothing reads it back: the export path rebuilds geometry from lod3.fbx plus
# skel_state, and the only two npz consumers in the repo (modal_app's
# export_clip_gltf and services/motion-api/motion_result.py) touch skel_state
# and shape_params and nothing else.
#
# `expr_params` is 0.02 MB and is here for the other reason: 72 facial
# expression coefficients per person per frame are the most face-shaped thing
# the system stores, they exist purely because the whole dict got pickled, and
# nothing has ever read them (docs/legal/rights-and-privacy.md section 6.2).
# Dropping the persistence costs no capability -- the model still emits them on
# demand if a future feature wants expression.
#
# ponytail: a denylist, not an allowlist. An allowlist would be smaller and
# would also silently break sibling branches that legitimately read
# bone_length_ratio / hand_crop_rect / foot_crop_rect out of the same npz.
# Deny only what has been verified unread.
UNREAD_PER_FRAME_KEYS = ("pred_vertices", "expr_params")


def _strip_unread(per_frame: list) -> list:
    return [
        {tid: {k: v for k, v in person.items() if k not in UNREAD_PER_FRAME_KEYS}
         for tid, person in frame.items()}
        if isinstance(frame, dict) else frame
        for frame in per_frame
    ]


def save_clip_result(result: dict, out_path: str) -> None:
    """Pack process_clip's output into one npz (object arrays for the
    per-frame dict list -- pickled, but this stays inside numpy's own npz
    container so the export stage doesn't need to trust an arbitrary pickle
    file on its own)."""
    if result.get("refused"):
        np.savez_compressed(
            out_path,
            refused=True,
            refusal_reason=result["refusal_reason"],
            refusal_message=result["refusal_message"],
            n_confident_dancers=result["n_confident_dancers"],
            sample_times_s=result["sample_times_s"],
            raw_detections=np.array(result["raw_detections"], dtype=object),
            frame_width=result.get("frame_width", 0),
            frame_height=result.get("frame_height", 0),
        )
        return
    np.savez_compressed(
        out_path,
        refused=False,
        sample_times_s=result["sample_times_s"],
        per_frame=np.array(_strip_unread(result["per_frame"]), dtype=object),
        # W9: smoothed motion + per-joint visibility/provenance, keyed by
        # track id. Additive -- `per_frame` still holds the raw estimates, and
        # the export stage keeps reading those until it is switched over.
        # Read it back with `np.load(...)["smoothed"].item()`: a dict stored
        # this way comes back as a 0-d object array, not a dict.
        #
        # NOT passed through `_strip_unread`, on purpose: it drops
        # `pred_vertices`/`expr_params`, which are per-person estimator
        # byproducts that only ever existed in `per_frame`. `smoothed` holds
        # the four per-joint tracks (visibility, suppression, prov_observed,
        # prov_interpolated) and nothing else, so there is nothing in it to
        # strip and filtering it would only risk deleting the one signal
        # INTEGRATION.md §3.3 is waiting on an owner for.
        smoothed=np.array(result.get("smoothed", {}), dtype=object),
        raw_detections=np.array(result["raw_detections"], dtype=object),
        confident_track_ids=np.array(result["confident_track_ids"], dtype=np.int64),
        faces=result["faces"],
        elapsed_s=result["elapsed_s"],
        peak_vram_bytes=result["peak_vram_bytes"],
        frame_width=result.get("frame_width", 0),
        frame_height=result.get("frame_height", 0),
        n_frames_ok=result["n_frames_ok"],
        n_frames_total=result["n_frames_total"],
    )
