# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Frame-by-frame clip pipeline: ffmpeg -> RTMO+ByteTrack -> SAM3DBodyEstimator.

Runs inside cv_image (Modal stage 5). Single-front-static camera. Per the
2026-09-18 scope revision (docs/PRD.md section 5), multiple dancers ARE in
the MVP: every detected person is reconstructed, keyed by ByteTrack id. What
stays out of scope here is cross-dancer consensus/identity-swap correction --
this file hands back per-track data as-is, including through a track-id
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

import cv2
import numpy as np


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
) -> dict:
    """Run the full detect+track+estimate pipeline over one clip.

    Returns a dict of numpy arrays. per_frame[i] is a {track_id: person_dict}
    mapping (empty dict, not None, for frames with zero detections -- a
    suppressed/absent frame, not fabricated data; see docs/PRD.md section 4's
    observed/uncertain/absent states, which this does not itself implement --
    the gate proves the pipeline hands back genuinely-missing data instead of
    a fabricated pose, it does not implement the suppression/hysteresis logic
    that consumes it (that is Milestone A's own Kalman + suppression chain,
    not gate scope). track_id is ByteTrack's raw id and can and will jump at
    an occlusion/re-entry or a dancer crossing -- no identity-continuity
    correction happens here, matching the multi-dancer scope revision's
    explicit non-goals (docs/PRD.md section 5).
    """
    import torch

    from sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
    from tools.build_detector import HumanDetector

    device = torch.device("cuda")
    print(f"loading SAM 3D Body + MHR ({checkpoint_path}, {mhr_path})")
    model, model_cfg = load_sam_3d_body(checkpoint_path, device=device, mhr_path=mhr_path)

    detector = HumanDetector(name="rtmo", device=device)
    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=model, model_cfg=model_cfg, human_detector=detector
    )

    print(f"extracting frames from {video_path} at {fps} fps")
    sample_times_s = extract_frames(video_path, frames_dir, fps=fps, max_seconds=max_seconds)
    frame_files = sorted(Path(frames_dir).glob("frame_*.jpg"))
    print(f"{len(frame_files)} frames")

    per_frame = []
    raw_detections = []  # for the "raw detector overlays visible" deliverable
    peak_vram_bytes = 0
    t_start = time.time()

    for i, (frame_path, t_s) in enumerate(zip(frame_files, sample_times_s)):
        img = cv2.imread(str(frame_path))
        det = detector.run_human_detection(img, bbox_thr=bbox_thr, default_to_full_image=False)
        raw_detections.append({
            "boxes": det["boxes"], "keypoints": det["keypoints"], "track_ids": det["track_ids"]
        })

        if len(det["boxes"]) == 0:
            # Genuinely no detection this frame -- G5's gate: no fabricated
            # pose. Recorded as absent (empty dict), not silently skipped, so
            # the sample time still exists in the output (PRD section 6).
            per_frame.append({})
            continue

        # Every detected dancer, not just one (docs/PRD.md section 5). One
        # process_one_image call, all boxes at once -- SAM 3D Body runs
        # per-crop internally, so this is N crops in one batch, not N calls.
        boxes = det["boxes"]
        outputs = estimator.process_one_image(
            img,
            bboxes=boxes,
            bbox_thr=bbox_thr,
            hand_box_source="yolo_pose",
        )
        per_frame.append(dict(zip(det["track_ids"].tolist(), outputs)))

        if torch.cuda.is_available():
            peak_vram_bytes = max(peak_vram_bytes, torch.cuda.max_memory_allocated())

        if i % 10 == 0:
            print(f"  frame {i}/{len(frame_files)}  t={t_s:.2f}s  "
                  f"dancers={len(boxes)}  vram_peak={peak_vram_bytes / 1e9:.2f}GB")

    elapsed_s = time.time() - t_start
    n_ok = sum(1 for f in per_frame if f)
    print(
        f"done: {n_ok}/{len(per_frame)} frames reconstructed, "
        f"{elapsed_s:.1f}s total ({len(per_frame) / elapsed_s:.2f} fps), "
        f"peak VRAM {peak_vram_bytes / 1e9:.2f} GB"
    )

    return {
        "sample_times_s": np.array(sample_times_s, dtype=np.float64),
        "per_frame": per_frame,  # list of {track_id: person_dict}, one per sample time
        "raw_detections": raw_detections,
        "faces": estimator.faces,
        "elapsed_s": elapsed_s,
        "peak_vram_bytes": peak_vram_bytes,
        "n_frames_ok": n_ok,
        "n_frames_total": len(per_frame),
    }


def save_clip_result(result: dict, out_path: str) -> None:
    """Pack process_clip's output into one npz (object arrays for the
    per-frame dict list -- pickled, but this stays inside numpy's own npz
    container so the export stage doesn't need to trust an arbitrary pickle
    file on its own)."""
    np.savez_compressed(
        out_path,
        sample_times_s=result["sample_times_s"],
        per_frame=np.array(result["per_frame"], dtype=object),
        raw_detections=np.array(result["raw_detections"], dtype=object),
        faces=result["faces"],
        elapsed_s=result["elapsed_s"],
        peak_vram_bytes=result["peak_vram_bytes"],
        n_frames_ok=result["n_frames_ok"],
        n_frames_total=result["n_frames_total"],
    )
