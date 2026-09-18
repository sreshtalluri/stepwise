# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for rtmo_detector.py's pure-numpy logic.

No ONNX session, GPU, rtmlib, or bytetracker needed -- postprocess_aligned and
associate_tracks are plain numpy, tested here with synthetic RTMO-shaped
outputs. Run: python tools/test_rtmo_detector.py
"""
import numpy as np

from rtmo_detector import associate_tracks, postprocess_aligned


def _fake_rtmo_outputs(boxes, scores, keypoints=None, num_kpts=17):
    """Build (det_outputs, pose_outputs) shaped like raw RTMO ONNX output,
    i.e. batch dim 0, N candidate detections before score-thresholding."""
    n = len(boxes)
    det_outputs = np.zeros((1, n, 5), dtype=np.float32)
    det_outputs[0, :, :4] = boxes
    det_outputs[0, :, 4] = scores
    pose_outputs = np.zeros((1, n, num_kpts, 3), dtype=np.float32)
    if keypoints is not None:
        pose_outputs[0] = keypoints
    return det_outputs, pose_outputs


def test_zero_detections_returns_genuinely_empty():
    det_outputs, pose_outputs = _fake_rtmo_outputs(
        boxes=np.zeros((0, 4), dtype=np.float32), scores=np.zeros((0,), dtype=np.float32)
    )
    boxes, scores, kpts, kpt_scores = postprocess_aligned(
        det_outputs, pose_outputs, ratio=1.0, nms_thr=0.45, score_thr=0.1
    )
    assert boxes.shape == (0, 4)
    assert kpts.shape == (0, 17, 2)
    assert not np.any(np.isnan(boxes)), "must be genuinely empty, not a fabricated zero pose"


def test_all_below_threshold_returns_empty_not_fabricated_pose():
    # upstream rtmlib fabricates np.zeros_like(keypoints[0]) here instead
    boxes = np.array([[10, 10, 50, 50]], dtype=np.float32)
    scores = np.array([0.05], dtype=np.float32)  # below score_thr
    det_outputs, pose_outputs = _fake_rtmo_outputs(boxes, scores)
    out_boxes, out_scores, kpts, kpt_scores = postprocess_aligned(
        det_outputs, pose_outputs, ratio=1.0, nms_thr=0.45, score_thr=0.1
    )
    assert len(out_boxes) == 0
    assert len(kpts) == 0


def test_boxes_and_keypoints_stay_aligned_after_score_filter():
    # Regression test for the exact upstream bug: `keep` indices from
    # multiclass_nms are relative to the score-thresholded subset, but
    # upstream applies them to the unfiltered keypoints/scores array. Build a
    # case where score-thresholding actually drops a candidate in the middle,
    # so a misaligned index would silently return the wrong person's box.
    boxes = np.array(
        [
            [0, 0, 10, 10],  # dropped: low score
            [100, 100, 150, 150],  # kept: person A
            [0, 0, 10, 10],  # dropped: low score
            [300, 300, 350, 350],  # kept: person B
        ],
        dtype=np.float32,
    )
    scores = np.array([0.01, 0.9, 0.01, 0.8], dtype=np.float32)
    keypoints = np.zeros((4, 17, 3), dtype=np.float32)
    keypoints[1, 9] = [120, 120, 0.9]  # person A's left wrist
    keypoints[3, 9] = [320, 320, 0.9]  # person B's left wrist
    det_outputs, pose_outputs = _fake_rtmo_outputs(boxes, scores, keypoints)

    out_boxes, out_scores, kpts, kpt_scores = postprocess_aligned(
        det_outputs, pose_outputs, ratio=1.0, nms_thr=0.45, score_thr=0.1
    )
    assert len(out_boxes) == 2
    # each surviving box's own keypoints must travel with it, not a neighbor's
    for box, kpt in zip(out_boxes, kpts):
        cx = (box[0] + box[2]) / 2
        wrist_x = kpt[9, 0]
        assert abs(cx - wrist_x) < 50, (
            f"box centered at x={cx} paired with wrist at x={wrist_x} -- misaligned"
        )


def test_wrist_indices_stay_coco17_shape():
    boxes = np.array([[0, 0, 100, 200]], dtype=np.float32)
    scores = np.array([0.9], dtype=np.float32)
    det_outputs, pose_outputs = _fake_rtmo_outputs(boxes, scores, num_kpts=17)
    out_boxes, out_scores, kpts, kpt_scores = postprocess_aligned(
        det_outputs, pose_outputs, ratio=1.0, nms_thr=0.45, score_thr=0.1
    )
    assert kpts.shape[1] == 17, "to_openpose=False must keep COCO-17 layout (wrists at 9/10)"


def test_associate_tracks_reattaches_correct_keypoints():
    # ByteTrack's Kalman-fused box will not exactly equal the raw detection
    # box; association must still find the right one by IoU, not by index.
    boxes = np.array([[100, 100, 150, 150], [300, 300, 350, 350]], dtype=np.float32)
    keypoints = np.zeros((2, 17, 2), dtype=np.float32)
    keypoints[0, 9] = [120, 120]
    keypoints[1, 9] = [320, 320]
    kpt_scores = np.full((2, 17), 0.9, dtype=np.float32)

    # tracked box for person B, slightly perturbed by the Kalman filter
    tracked_boxes = np.array([[302, 301, 349, 348]], dtype=np.float32)

    out_boxes, out_kpts = associate_tracks(tracked_boxes, boxes, keypoints, kpt_scores, num_kpts=17)
    assert len(out_boxes) == 1
    assert tuple(out_kpts[0, 9, :2]) == (320.0, 320.0), "must match person B, not person A"


def test_associate_tracks_drops_unmatched_track():
    tracked_boxes = np.array([[900, 900, 950, 950]], dtype=np.float32)  # no overlap with anything
    boxes = np.array([[0, 0, 50, 50]], dtype=np.float32)
    keypoints = np.zeros((1, 17, 2), dtype=np.float32)
    kpt_scores = np.zeros((1, 17), dtype=np.float32)
    out_boxes, out_kpts = associate_tracks(tracked_boxes, boxes, keypoints, kpt_scores, num_kpts=17)
    assert len(out_boxes) == 0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
