# Provenance

Vendored from <https://github.com/yangtiming/Fast-SAM-3D-Body>, commit
`808b53c` (2026-06-18), the HEAD of `main` at the time of vendoring and the
commit pinned in `docs/PRD.md` (no releases exist upstream, so a commit SHA is
the only stable reference). License: MIT (see `LICENSE`, retained verbatim per
its terms).

## Why vendored instead of forked

Forking to a new public GitHub repo was avoided for this pass (creating a
public surface needs explicit sign-off); the pinned commit is copied directly
into this repo instead, which gives the same "our own copy to modify" outcome.
If a real upstream fork is wanted later, this directory's diff against
`808b53c` is exactly the patch to carry over.

## What was excluded and why

Only the pieces this project's pipeline (RTMO detect+track -> SAM 3D Body ->
MHR, single clip, no robot teleop) actually touches were copied:

- `sam_3d_body/` -- the model package, unmodified except `tools/build_detector.py`.
- `tools/` -- detector/segmentor/FOV builders and vis utils.
- `checkpoints/sam-3d-body-dinov3/model_config.yaml` -- config referenced by the loader.
- `LICENSE`, `README.md`, `demo.py` -- reference/citation, kept for context.
- `setup_env.sh` -- kept for documentation, edited per `docs/PRD.md` G3 (see
  the file's own header comment); the real build is Modal's `cv_image` in
  `modal_app.py`, which does not execute this script.

Not vendored, all unrelated to a dance-video pipeline: `mhr2smpl/` (SMPL
conversion for humanoid robot teleop), `mocap/` and `record_realsense*.py`
(realtime RealSense camera streaming), `notebook/` (demo notebook), `data/`
(dataset prep scripts), `assets/` (README marketing images/PDF),
`convert_*_trt.py` and `build_tensorrt.sh` (TensorRT engine conversion --
skipped entirely per G4), `demo_human.py` and `profile_nsight.py` (this
project writes its own video pipeline instead of adapting the single-image
demo scripts).

## Modifications made here (beyond upstream `808b53c`)

- `tools/build_detector.py`: added an `"rtmo"` branch to `HumanDetector`,
  registering `tools/rtmo_detector.py`'s adapter alongside the existing
  `vitdet`/`yolo`/`yolo_pose` entries. No other line in this file changed.
- `tools/rtmo_detector.py`: new file, not upstream. RTMO + ByteTrack adapter
  (see its own docstring for the specific rtmlib bug it works around).
- `setup_env.sh`: removed `ultralytics`, `tensorrt-cu12*`, `smplx`/`chumpy`,
  MoGe, `pyzmq`/`pyrealsense2`; added `rtmlib`/`bytetracker`/`onnxruntime-gpu`.
- Nothing in `sam_3d_body/models/meta_arch/sam3d_body.py` was touched --
  `_get_hand_box_from_yolo_pose` (~line 3430) is pure numpy keyed to COCO-17
  wrist indices and needs no ultralytics-specific change.
