# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""RTMO (rtmlib, ONNXRuntime CUDA) + upstream ByteTrack detector adapter.

Registered as HumanDetector(name="rtmo") in tools/build_detector.py, matching
the existing dict-returning "yolo_pose" contract so
sam_3d_body_estimator.py / sam3d_body.py need no changes (see PROVENANCE.md).

Why this file exists -- rtmlib.RTMO will not hand you what you need as-is:

1. RTMO.postprocess (rtmlib/tools/pose_estimation/rtmo.py) computes per-person
   boxes and scores via multiclass_nms, uses the result only to get NMS `keep`
   indices, then returns just (keypoints, scores) -- the boxes are discarded.
   Worse, those `keep` indices are relative to the *score-thresholded* subset
   (multiclass_nms's internal `boxes[cls_scores > score_thr]`), but upstream
   applies them to the *un-thresholded* `keypoints`/`scores` arrays -- so
   `keypoints[keep]` silently misaligns boxes and keypoints whenever score_thr
   filters anything out. RTMOWithBoxes redoes the score-filter -> NMS pipeline
   itself so every array is filtered in the same order and stays paired, and
   returns the boxes instead of throwing them away.
2. On zero detections, upstream fabricates a single all-zero pose
   (`np.zeros_like(keypoints[0])`) rather than returning nothing.
   sam_3d_body_estimator.py checks `len(boxes) == 0` to skip a frame with no
   detections; the fabricated pose defeats that check and would hand the
   estimator a fake person standing at (0, 0). RTMOWithBoxes returns genuinely
   empty arrays instead.

`to_openpose` stays False: sam3d_body.py's _get_hand_box_from_yolo_pose keys
wrists at COCO-17 indices 9/10, which the OpenPose remap would move.

Coordinates: RTMO's own preprocess/postprocess already divides by `ratio` to
convert from padded model-input space back to original-image pixels, so boxes
handed to ByteTrack are already in full-frame coordinates. ByteTrack's
xyxy2ltwh only reformats (x1,y1,x2,y2) -> (left,top,w,h); it does not rescale.
Nothing downstream should rescale coordinates a second time.
"""
from __future__ import annotations

import numpy as np
import onnxruntime as ort
from rtmlib.tools.object_detection.post_processings import nms
from rtmlib.tools.pose_estimation.rtmo import RTMO

# rtmlib's BaseTool creates the ORT session directly and never calls this.
# ORT >=1.21 needs an explicit preload (onnxruntime.ai/docs/execution-
# providers/CUDA-ExecutionProvider.html) rather than relying on
# ldconfig/LD_LIBRARY_PATH discovery of torch's pip-installed CUDA/cuDNN.
# Pinned onnxruntime-gpu here is 1.20.2 (see modal_app.py's cv_image -- newer
# releases require CUDA 13, incompatible with this image's CUDA 12.4), which
# predates preload_dlls and doesn't need it (ldconfig registration in
# modal_app.py's image covers discovery instead) -- guarded for whichever
# version actually ends up installed.
if hasattr(ort, "preload_dlls"):
    ort.preload_dlls()

# Lower than rtmlib's RTMO default of 0.7. ByteTrack's own two-tier matching
# (high-confidence detections spawn/confirm tracks; low-confidence ones only
# extend an existing track) is what actually benefits from low-score
# candidates surviving past this point -- if we filter at RTMO's default
# threshold there is nothing left for ByteTrack's second-stage match to use
# during a partial occlusion, and a track drops instead of persisting through
# it. See docs/PRD.md G3/G5.
DEFAULT_SCORE_THR = 0.1
DEFAULT_NMS_THR = 0.45

# RTMO-m/body7 @ 640x640, per docs/PRD.md's pipeline table. This is rtmlib's
# own Body.RTMO_MODE["balanced"]["pose"] URL (openmmlab-hosted, Apache-2.0) --
# rtmlib takes a URL or local path here, not a bare alias like "rtmo-m".
RTMO_M_BODY7_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
    "rtmo-m_16xb16-600e_body7-640x640-39e78cc4_20231211.zip"
)

_EMPTY_BOXES = np.zeros((0, 4), dtype=np.float32)


def _empty(num_kpts: int):
    return (
        _EMPTY_BOXES.copy(),
        np.zeros((0,), dtype=np.float32),
        np.zeros((0, num_kpts, 2), dtype=np.float32),
        np.zeros((0, num_kpts), dtype=np.float32),
    )


def postprocess_aligned(det_outputs, pose_outputs, ratio, nms_thr, score_thr):
    """Pure-numpy core of RTMOWithBoxes, split out so it is unit-testable
    without an ONNX session (see tools/test_rtmo_detector.py)."""
    boxes = det_outputs[0, :, :4] / ratio
    scores = det_outputs[0, :, 4]
    keypoints = pose_outputs[0, :, :, :2] / ratio
    kpt_scores = pose_outputs[0, :, :, 2]
    num_kpts = keypoints.shape[1]

    valid = scores > score_thr
    if not valid.any():
        return _empty(num_kpts)
    boxes, scores = boxes[valid], scores[valid]
    keypoints, kpt_scores = keypoints[valid], kpt_scores[valid]

    keep = nms(boxes, scores, nms_thr)
    if len(keep) == 0:
        return _empty(num_kpts)
    return boxes[keep], scores[keep], keypoints[keep], kpt_scores[keep]


class RTMOWithBoxes(RTMO):
    """RTMO that returns correctly-aligned (boxes, scores, keypoints, kpt_scores)."""

    def __call__(self, image, nms_thr: float = None, score_thr: float = None):
        assert not self.to_openpose, "to_openpose must stay False (see module docstring)"
        nms_thr = nms_thr if nms_thr is not None else self.nms_thr
        score_thr = score_thr if score_thr is not None else self.score_thr

        padded, ratio = self.preprocess(image)
        det_outputs, pose_outputs = self.inference(padded)
        return postprocess_aligned(det_outputs, pose_outputs, ratio, nms_thr, score_thr)


def _iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise IoU, a: (N,4), b: (M,4) xyxy -> (N,M)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    area_a = (a[:, 2] - a[:, 0]).clip(0) * (a[:, 3] - a[:, 1]).clip(0)
    area_b = (b[:, 2] - b[:, 0]).clip(0) * (b[:, 3] - b[:, 1]).clip(0)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = (x2 - x1).clip(0) * (y2 - y1).clip(0)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)


def associate_tracks(tracked_boxes, boxes, keypoints, kpt_scores, num_kpts, track_ids=None, iou_thr=0.1):
    """Re-attach this frame's keypoints to ByteTrack's (box-only) output by
    nearest IoU. Pure numpy, split out for unit testing.

    track_ids, if given, is (len(tracked_boxes),) and is filtered/returned
    alongside boxes/keypoints -- multiple dancers are in scope (docs/PRD.md
    section 5, 2026-09-18 revision), so callers need a stable per-person id,
    not just "however many boxes this frame happened to have".
    """
    empty_ids = np.zeros((0,), dtype=np.int64)
    if len(tracked_boxes) == 0 or len(boxes) == 0:
        return _EMPTY_BOXES.copy(), np.zeros((0, num_kpts, 3), dtype=np.float32), empty_ids

    iou = _iou_matrix(tracked_boxes, boxes)
    best = iou.argmax(axis=1)
    matched = iou[np.arange(len(tracked_boxes)), best] > iou_thr

    out_boxes = tracked_boxes[matched]
    out_keypoints = np.concatenate(
        [keypoints[best[matched]], kpt_scores[best[matched], :, None]], axis=-1
    )
    out_ids = track_ids[matched] if track_ids is not None else empty_ids
    return out_boxes, out_keypoints.astype(np.float32), out_ids


class RTMODetector:
    """RTMO + ByteTrack. ByteTrack only tracks boxes, so each frame's tracked
    boxes (Kalman-fused, not identical to the raw detection) are re-associated
    back to this frame's raw keypoints by IoU -- a matched track's box is
    close enough to its detection's box for that association to be unambiguous
    in practice (ponytail: greedy nearest-IoU, not a full assignment solver --
    fine at the person counts this product ever sees; revisit if false matches
    show up with several overlapping people).
    """

    def __init__(
        self,
        onnx_model: str = RTMO_M_BODY7_URL,
        device: str = "cuda",
        model_input_size: tuple = (640, 640),
        score_thr: float = DEFAULT_SCORE_THR,
        nms_thr: float = DEFAULT_NMS_THR,
        track_thresh: float = 0.25,
        track_buffer: int = 60,
        match_thresh: float = 0.8,
        frame_rate: int = 15,
        **kwargs,
    ):
        self.rtmo = RTMOWithBoxes(
            onnx_model,
            model_input_size=model_input_size,
            nms_thr=nms_thr,
            score_thr=score_thr,
            to_openpose=False,
            backend="onnxruntime",
            device=device,
        )
        self._tracker_args = dict(
            track_thresh=track_thresh,
            track_buffer=track_buffer,
            match_thresh=match_thresh,
            frame_rate=frame_rate,
        )
        self.reset()

    def reset(self) -> None:
        """Fresh ByteTrack state. The ONNX session is reused across clips by a
        warm container; track ids and Kalman state must never be. The id
        counter is class-level in bytetracker, so a new BYTETracker alone would
        number a warm container's second clip from where the first stopped."""
        from bytetracker import BYTETracker
        from bytetracker.basetrack import BaseTrack

        BaseTrack._count = 0
        self.tracker = BYTETracker(**self._tracker_args)

    def run_human_detection(
        self,
        img: np.ndarray,
        det_cat_id: int = 0,
        bbox_thr: float = DEFAULT_SCORE_THR,
        nms_thr: float = DEFAULT_NMS_THR,
        default_to_full_image: bool = False,
        **kwargs,
    ) -> dict:
        num_kpts = 17  # COCO-17, to_openpose=False
        boxes, scores, keypoints, kpt_scores = self.rtmo(
            img, nms_thr=nms_thr, score_thr=bbox_thr
        )

        dets = (
            np.concatenate(
                [boxes, scores[:, None], np.full((len(boxes), 1), det_cat_id, dtype=np.float32)],
                axis=1,
            )
            if len(boxes)
            else np.zeros((0, 6), dtype=np.float32)
        )
        tracked = self.tracker.update(dets)
        tracked_boxes = tracked[:, :4].astype(np.float32) if len(tracked) else tracked
        track_ids = tracked[:, 4].astype(np.int64) if len(tracked) else None
        out_boxes, out_keypoints, out_ids = associate_tracks(
            tracked_boxes, boxes, keypoints, kpt_scores, num_kpts, track_ids=track_ids
        )
        # "track_ids" is an extra key beyond the {"boxes","keypoints"} contract
        # HumanDetector/sam_3d_body_estimator.py read -- harmless there, and
        # this is what process_clip.py uses to key per-dancer output across
        # frames (docs/PRD.md section 5's multi-dancer MVP).
        return {"boxes": out_boxes, "keypoints": out_keypoints, "track_ids": out_ids}
