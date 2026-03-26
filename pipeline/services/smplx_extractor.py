"""SMPL-X/SMPL body model extraction with mock fallback.

Set USE_REAL_SMPLX=true to use 4D Humans (HMR 2.0) for real pose extraction.
Requires GPU and 4D Humans installation (pip install -e ".[all]" from the 4D-Humans repo).

The real extractor patches 4D Humans to skip SMPL body model initialization,
extracting rotation parameters directly from the neural network head.
This avoids requiring the non-commercial SMPL .pkl model file.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pipeline.models.schema import PersonPose, SmplxParams


@dataclass
class SmplxExtractionResult:
    """Result of SMPL-X extraction for all persons across all frames."""
    person_count: int
    person_poses: list[PersonPose] = field(default_factory=list)


def _rotmat_to_axis_angle(rotmat: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to axis-angle (3 values).

    Uses scipy for robust conversion handling edge cases
    (identity rotation, 180-degree rotations, etc.)
    """
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(rotmat).as_rotvec()


def _extract_4d_humans(video_path: str, total_frames: int, fps: float) -> SmplxExtractionResult:
    """Extract SMPL params using 4D Humans (HMR 2.0).

    Pipeline:
    1. ViTDet person detection per frame -> bounding boxes
    2. HMR2 inference on person crops -> rotation matrices
    3. Convert rotation matrices to axis-angle
    4. Track persons across frames using bbox IoU

    The HMR2 model is patched to skip SMPL body model initialization:
    - model.smpl is set to None
    - forward_step extracts pred_smpl_params from smpl_head directly
    - No SMPL .pkl file required
    """
    try:
        import torch
        import cv2
        from hmr2.models import load_hmr2, download_models, DEFAULT_CHECKPOINT
        from hmr2.configs import CACHE_DIR_4DHUMANS
        from hmr2.datasets.vitdet_dataset import ViTDetDataset
        from hmr2.utils import recursive_to
    except ImportError:
        raise NotImplementedError(
            "4D Humans not installed. Install with:\n"
            "  git clone https://github.com/shubham-goel/4D-Humans\n"
            "  cd 4D-Humans && pip install -e '.[all]' --no-build-isolation\n"
            "Set USE_REAL_SMPLX=false to use mock data instead."
        )

    # Download model weights if needed
    download_models(CACHE_DIR_4DHUMANS)

    # Load model with patched SMPL initialization
    model, model_cfg = load_hmr2(DEFAULT_CHECKPOINT)

    # Patch: disable SMPL body model (we only need rotation params)
    model.smpl = None
    model = model.to("cuda")
    model.eval()

    # Initialize person detector
    from detectron2.config import get_cfg
    from detectron2 import model_zoo
    from detectron2.engine import DefaultPredictor

    det_cfg = get_cfg()
    det_cfg.merge_from_file(model_zoo.get_config_file("new_baselines/mask_rcnn_vitdet_b_100ep.py"))
    det_cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5
    det_cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url("new_baselines/mask_rcnn_vitdet_b_100ep.py")
    detector = DefaultPredictor(det_cfg)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    all_person_poses: list[PersonPose] = []
    person_count = 0

    frame_idx = 0
    while frame_idx < total_frames:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = round(frame_idx / fps, 4)

        # Detect persons
        det_output = detector(frame)
        instances = det_output["instances"]
        # Filter for person class (class 0 in COCO)
        person_mask = instances.pred_classes == 0
        boxes = instances.pred_boxes.tensor[person_mask].cpu().numpy()

        if len(boxes) == 0:
            frame_idx += 1
            continue

        person_count = max(person_count, len(boxes))

        # Run HMR2 on detected persons
        dataset = ViTDetDataset(model_cfg, frame, boxes)
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=len(boxes), shuffle=False, num_workers=0)

        for batch in dataloader:
            batch = recursive_to(batch, "cuda")
            with torch.no_grad():
                # Extract features and predict SMPL params
                conditioning_feats = model.backbone(batch["img"][:, :, :, 32:-32])
                pred_smpl_params, pred_cam, _ = model.smpl_head(conditioning_feats)

                # pred_smpl_params contains:
                # 'global_orient': (B, 1, 3, 3) rotation matrices
                # 'body_pose': (B, 23, 3, 3) rotation matrices
                # 'betas': (B, 10) shape coefficients

                batch_size = pred_smpl_params["body_pose"].shape[0]

                for i in range(batch_size):
                    # Convert rotation matrices to axis-angle
                    go = pred_smpl_params["global_orient"][i, 0].cpu().numpy()  # (3,3)
                    bp = pred_smpl_params["body_pose"][i].cpu().numpy()  # (23,3,3)
                    betas = pred_smpl_params["betas"][i].cpu().numpy()  # (10,)

                    go_aa = _rotmat_to_axis_angle(go)  # (3,)
                    bp_aa = np.array([_rotmat_to_axis_angle(bp[j]) for j in range(23)])  # (23,3)

                    params = SmplxParams(
                        betas=[round(float(b), 4) for b in betas],
                        body_pose=[round(float(v), 4) for v in bp_aa.flatten()],  # 69 values
                        left_hand_pose=[],
                        right_hand_pose=[],
                        global_orient=[round(float(v), 4) for v in go_aa],
                        transl=[0.0, 0.0, 0.0],  # TODO: derive from pred_cam_t
                    )

                    all_person_poses.append(PersonPose(
                        person_id=i,  # Simple: use detection order (TODO: proper tracking via PHALP)
                        frame=frame_idx,
                        timestamp=timestamp,
                        smplx_params=params,
                    ))

        frame_idx += 1

    cap.release()

    return SmplxExtractionResult(
        person_count=max(person_count, 1),
        person_poses=all_person_poses,
    )


def _generate_mock_smplx(
    total_frames: int,
    fps: float,
    num_people: int = 1,
) -> SmplxExtractionResult:
    """Generate plausible mock SMPL parameters.

    Creates smooth motion by varying body_pose and transl sinusoidally.
    Each person gets a fixed body shape (betas) and varying poses.
    Outputs SMPL format (23 joints x 3 = 69 values) to match 4D Humans.
    """
    person_poses: list[PersonPose] = []
    cycle_frames = int(fps * 2)  # 2-second movement cycle

    for person_id in range(num_people):
        # Fixed body shape per person (slight variation)
        betas = [0.0] * 10
        betas[0] = (person_id - num_people / 2) * 0.5  # height variation

        # Lateral offset so people don't overlap
        base_x = (person_id - (num_people - 1) / 2) * 0.8

        for frame_idx in range(total_frames):
            t = frame_idx / fps
            phase = (frame_idx % cycle_frames) / cycle_frames
            angle = math.sin(phase * 2 * math.pi)

            # Body pose: 23 joints x 3 axis-angle = 69 values (SMPL format)
            # Animate shoulders (joints 16,17 in SMPL ordering -> indices 48-53)
            body_pose = [0.0] * 69
            body_pose[48] = angle * 0.5   # left shoulder Z rotation
            body_pose[51] = -angle * 0.5  # right shoulder Z rotation
            # Slight hip sway
            body_pose[0] = math.sin(phase * 4 * math.pi) * 0.1

            # Global orientation: facing forward with slight rotation
            global_orient = [0.0, math.sin(phase * 2 * math.pi) * 0.1, 0.0]

            # Translation: slight lateral sway
            transl = [
                base_x + math.sin(phase * 4 * math.pi) * 0.05,
                0.95,
                0.0,
            ]

            params = SmplxParams(
                betas=betas,
                body_pose=[round(v, 4) for v in body_pose],
                left_hand_pose=[],
                right_hand_pose=[],
                global_orient=[round(v, 4) for v in global_orient],
                transl=[round(v, 4) for v in transl],
            )

            person_poses.append(PersonPose(
                person_id=person_id,
                frame=frame_idx,
                timestamp=round(t, 4),
                smplx_params=params,
            ))

    return SmplxExtractionResult(
        person_count=num_people,
        person_poses=person_poses,
    )


async def extract_smplx(
    video_path: str | Path,
    total_frames: int,
    fps: float,
    num_people: int = 1,
) -> SmplxExtractionResult:
    """Extract SMPL body params from video.

    Uses 4D Humans when USE_REAL_SMPLX=true, otherwise returns mock data.
    """
    use_real = os.environ.get("USE_REAL_SMPLX", "false").lower() in ("true", "1", "yes")

    if use_real:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _extract_4d_humans, str(video_path), total_frames, fps
        )

    return _generate_mock_smplx(total_frames, fps, num_people)
