#!/bin/bash
set -e

# === SAM 3D Body Environment Setup (following official guide) ===
#
# EDITED for stepwise (see docs/PRD.md G2/G3): the upstream script installs
# ultralytics (AGPL-3.0, cannot legally combine with the SAM License in one
# program), tensorrt-cu12* (not needed -- rtmlib has no TensorRT branch and
# the gate skips TensorRT entirely per G4), and smplx/chumpy (SMPL-X body
# model, unused -- this pipeline runs SAM 3D Body -> MHR only). All three are
# removed below. RTMO replaces ultralytics for detection (see tools/rtmo_detector.py).
# This script documents the environment for reference; the actual build runs
# via services/motion-api/modal_app.py's cv_image, not this conda script.

# Step 1: Create conda env
conda create -n fast_sam_3d_body python=3.11 -y
eval "$(conda shell.bash hook)"
conda activate fast_sam_3d_body

# Step 2: Install CUDA toolkit 12.4 (needed for detectron2 compilation)
echo "=== Installing CUDA toolkit ==="
conda install -c nvidia/label/cuda-12.4.0 cuda-toolkit -y

# Step 3: Install PyTorch (CUDA 12.4)
echo "=== Installing PyTorch ==="
pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 \
    --extra-index-url https://download.pytorch.org/whl/cu124

# Step 4: Install Python dependencies
echo "=== Installing Python dependencies ==="
pip install pytorch-lightning pyrender opencv-python yacs scikit-image einops timm \
    dill pandas rich hydra-core hydra-submitit-launcher hydra-colorlog pyrootutils \
    webdataset chump networkx==3.2.1 roma joblib seaborn wandb appdirs appnope \
    ffmpeg cython jsonlines pytest xtcocotools loguru optree fvcore black \
    pycocotools tensorboard huggingface_hub

# Step 5: Install Detectron2
echo "=== Installing Detectron2 ==="
export CUDA_HOME=$CONDA_PREFIX
pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' \
    --no-build-isolation --no-deps

# Step 6: [REMOVED] ultralytics -- AGPL-3.0, replaced by RTMO (Apache-2.0) via
# rtmlib. See tools/rtmo_detector.py and tools/build_detector.py's "rtmo" entry.

# Step 7: [REMOVED] MoGe -- FOV/depth estimator, unused in the gate. The MVP
# camera model is "single_front_static" (docs/PRD.md); FOV estimation is
# optional in demo.py (only loaded if --fov_name is passed) and not worth the
# extra dependency until the contract needs it.

# Step 8: Install ONNX + ONNXRuntime CUDA (for RTMO; no TensorRT -- rtmlib has
# no TensorRT branch, and G4 skips TensorRT in the gate entirely)
echo "=== Installing ONNX + ONNXRuntime CUDA ==="
pip install onnx onnxruntime-gpu

# Step 8b: RTMO + ByteTrack for detection/tracking.
# --no-deps on rtmlib: its own requires_dist lists plain "onnxruntime" (CPU),
# not onnxruntime-gpu. Installing both puts CPU and GPU builds' files in the
# same onnxruntime/ site-packages directory, and CUDAExecutionProvider
# silently vanishes from get_available_providers() with no error -- only a
# "multiple onnxruntime packages installed to the same location" warning.
# numpy/opencv/tqdm are already covered by earlier steps.
pip install rtmlib --no-deps
pip install bytetracker

# Also call onnxruntime.preload_dlls() before constructing any ORT session
# (see tools/rtmo_detector.py) -- rtmlib's BaseTool builds the session
# directly and never calls it, and ORT >=1.21 needs the explicit preload
# rather than relying on ldconfig/LD_LIBRARY_PATH discovery of torch's
# pip-installed CUDA/cuDNN.

pip install numpy scipy opencv-python tqdm
# [REMOVED] smplx, chumpy -- SMPL-X body model, unused (this pipeline runs
# SAM 3D Body -> MHR only, never SMPL/SMPL-X).
# [REMOVED] pyzmq, pyrealsense2 -- realtime RealSense camera streaming,
# unused for a batch video-clip pipeline.

# Step 9: Install SAM3 (optional, uncomment if needed)
# echo "=== Installing SAM3 ==="
# cd /tmp
# rm -rf sam3
# git clone https://github.com/facebookresearch/sam3.git
# cd sam3
# pip install -e .
# pip install decord psutil

echo "=== Environment setup complete! ==="
