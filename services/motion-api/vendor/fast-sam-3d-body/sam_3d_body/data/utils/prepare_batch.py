# Copyright (c) Meta Platforms, Inc. and affiliates.

import numpy as np
import torch
from torch.utils.data import default_collate


class NoCollate:
    def __init__(self, data):
        self.data = data


def prepare_batch(
    img,
    transform,
    boxes,
    masks=None,
    masks_score=None,
    cam_int=None,
):
    """A helper function to prepare data batch for SAM 3D Body model inference."""
    height, width = img.shape[:2]

    # construct batch data samples
    data_list = []
    for idx in range(boxes.shape[0]):
        data_info = dict(img=img)
        data_info["bbox"] = boxes[idx]  # shape (4,)
        data_info["bbox_format"] = "xyxy"

        if masks is not None:
            data_info["mask"] = masks[idx].copy()
            if masks_score is not None:
                data_info["mask_score"] = masks_score[idx]
            else:
                data_info["mask_score"] = np.array(1.0, dtype=np.float32)
        else:
            data_info["mask"] = np.zeros((height, width, 1), dtype=np.uint8)
            data_info["mask_score"] = np.array(0.0, dtype=np.float32)

        data_list.append(transform(data_info))

    batch = default_collate(data_list)

    max_num_person = batch["img"].shape[0]
    for key in [
        "img",
        "img_size",
        "ori_img_size",
        "bbox_center",
        "bbox_scale",
        "bbox",
        "affine_trans",
        "mask",
        "mask_score",
    ]:
        if key in batch:
            batch[key] = batch[key].unsqueeze(0).float()
    if "mask" in batch:
        batch["mask"] = batch["mask"].unsqueeze(2)
    batch["person_valid"] = torch.ones((1, max_num_person))

    if cam_int is not None:
        batch["cam_int"] = cam_int.to(batch["img"])
    else:
        # Default camera intrinsics according image size
        batch["cam_int"] = torch.tensor(
            [
                [
                    [(height**2 + width**2) ** 0.5, 0, width / 2.0],
                    [0, (height**2 + width**2) ** 0.5, height / 2.0],
                    [0, 0, 1],
                ]
            ],
        ).to(batch["img"])

    batch["img_ori"] = [NoCollate(img)]
    return batch


# Keys prepare_batch lays out as [1, num_person, ...]: people are along dim 1.
PERSON_KEYS = (
    "img", "img_size", "ori_img_size", "bbox_center", "bbox_scale",
    "bbox", "affine_trans", "mask", "mask_score", "person_valid",
)


def concat_person_batches(parts):
    """Several prepare_batch results as one batch, people along dim 1.

    For frames of ONE clip (stepwise, docs/research/pipeline-latency.md #7):
    same size and camera, so everything that is not per person (cam_int) is
    the first frame's. The model already takes N people in one image; this
    makes N people from several images look exactly like that, so one forward
    pass serves a run of frames. Measured on an L40S: 246 ms a frame alone,
    ~100 ms a frame eight at a time.
    """
    if len(parts) == 1:
        return parts[0]
    out = dict(parts[0])
    for key in PERSON_KEYS:
        if key in out:
            out[key] = torch.cat([p[key] for p in parts], dim=1)
    if "img_ori" in out:
        out["img_ori"] = [x for p in parts for x in p["img_ori"]]
    return out


def prepare_batch_frames(imgs, counts, transform, boxes, cam_int=None, flip=False):
    """prepare_batch for people spread over frames: `boxes` holds counts[i]
    people of imgs[i], in order, and each crop is cut from its own frame.
    `flip` mirrors every frame first (the left-hand crops)."""
    parts, start = [], 0
    for img, n in zip(imgs, counts):
        if n:
            parts.append(prepare_batch(
                img[:, ::-1] if flip else img, transform, boxes[start:start + n],
                cam_int=None if cam_int is None else cam_int.clone(),
            ))
        start += n
    return concat_person_batches(parts)
