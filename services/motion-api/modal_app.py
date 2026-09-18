"""Modal infrastructure for the stepwise motion pipeline.

Staged deliberately. Each stage runs on its own so a failure tells you *which*
thing broke instead of dumping a wall of pip output:

    modal run modal_app.py::verify_gpu        # stage 1: does CUDA work at all
    modal run modal_app.py::download_weights  # stage 2: gated access + cache (CPU, cents)
    modal run modal_app.py::inspect_weights   # stage 3: what did we actually get

Stage 2 needs no GPU. Run it first: it proves the HuggingFace gate was granted
and caches the weights into a Volume so later GPU runs start warm.

Environment pins come from docs/PRD.md (G3) and are not arbitrary.
Fast-SAM-3D-Body's setup script requires Python 3.11 / Torch 2.5.1 / cu124
because Detectron2 compiles against that CUDA toolkit. pymomentum is
deliberately NOT installed here: its wheels target Python 3.12/3.13 with Torch
2.8, which is incompatible with this image. glTF export gets its own image.
"""

import os

import modal

APP_NAME = "stepwise-motion"

# Modal validates every function's GPU request when the app loads, so a GPU spec
# anywhere blocks even CPU-only functions if the account has no payment method.
# Override to run the CPU stages (download_weights, inspect_weights) before
# billing is configured:  STEPWISE_GPU= modal run modal_app.py::download_weights
GPU_TIER = os.environ.get("STEPWISE_GPU", "L40S") or None

# Gated. Access must be granted at huggingface.co/facebook/sam-3d-body-dinov3
# to the same account the HF_TOKEN belongs to.
SAM3D_REPO = "facebook/sam-3d-body-dinov3"
SAM3D_FALLBACK = "facebook/sam-3d-body-vith"

app = modal.App(APP_NAME)

# Persists between runs, so multi-GB weights download exactly once.
weights = modal.Volume.from_name("stepwise-weights", create_if_missing=True)
WEIGHTS_DIR = "/weights"

# evaluation/clips.yaml is the manifest (versioned); the actual video bytes
# live only here, fetched by evaluation/fetch.py. See evaluation/README.md.
eval_clips = modal.Volume.from_name("stepwise-eval", create_if_missing=True)
CLIPS_DIR = "/clips"

# Pipeline output (npz per clip) -- separate from weights/eval so a results
# wipe never risks the multi-GB downloads.
results = modal.Volume.from_name("stepwise-results", create_if_missing=True)
RESULTS_DIR = "/results"

# Modal resolves every Secret referenced anywhere in the app at load time, so a
# missing 'huggingface' secret would block even functions that never touch it
# (verify_gpu, for one). Degrade gracefully: stage 1 stays runnable before the
# token exists, and download_weights raises its own clear error if it is absent.
try:
    HF_SECRET = [modal.Secret.from_name("huggingface")]
except Exception:  # noqa: BLE001 -- any lookup failure means "not configured yet"
    HF_SECRET = []

# Light image for stages 1-3: just enough to prove CUDA and pull weights.
# The heavy CV stack lands in a separate image once this much is known good.
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "huggingface_hub[hf_transfer]==0.35.3",
        "torch==2.5.1",
        "numpy<2",
    )
    # hf_transfer does multipart downloads; meaningful for multi-GB checkpoints.
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HOME": WEIGHTS_DIR + "/hf"})
)


VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor", "fast-sam-3d-body")

# Real CV image (stage 4+). CUDA *devel* base, not debian_slim: Detectron2
# compiles a CUDA extension at install time and needs nvcc + CUDA_HOME, which
# a runtime-only base image does not have. TORCH_CUDA_ARCH_LIST is set
# explicitly (L40S = compute capability 8.9) so the compile does not need a
# GPU attached to the build step -- it would otherwise call
# torch.cuda.get_device_capability(), which fails with no GPU visible.
#
# Pins from docs/PRD.md G3: Python 3.11, torch 2.5.1+cu124 -- Detectron2's
# pinned commit compiles against exactly that CUDA toolkit version. Do NOT
# install pymomentum here (needs Python 3.12/3.13 + torch 2.8); glTF export
# is a separate image (see gltf_image).
cv_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "wget", "ffmpeg", "libgl1", "libglib2.0-0", "build-essential", "ninja-build")
    .env({"CUDA_HOME": "/usr/local/cuda", "TORCH_CUDA_ARCH_LIST": "8.9"})
    .pip_install("setuptools", "wheel")  # needed for --no-build-isolation installs below
    .pip_install(
        "torch==2.5.1+cu124",
        "torchvision==0.20.1+cu124",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .run_commands(
        # onnxruntime-gpu doesn't vendor cuDNN/cuBLAS itself -- it dlopens
        # them at CUDA-session-creation time, and silently drops
        # CUDAExecutionProvider from get_available_providers() if it can't
        # find them (no error; verify_cv_stack's own assertion is what caught
        # this). torch's pip install above already pulled in nvidia-cudnn-cu12
        # etc. as its own dependencies, but pip doesn't put them on the
        # system linker path -- register every nvidia-*-cu12 package's lib/
        # dir with ldconfig so any process can find them, not just torch.
        "python3 -c \"import glob; print('\\n'.join(glob.glob('/usr/local/lib/python3.11/site-packages/nvidia/*/lib')))\" "
        "> /etc/ld.so.conf.d/nvidia-pip.conf && ldconfig",
    )
    .pip_install(
        # From setup_env.sh's Step 4, minus smplx/chumpy (unused -- no SMPL-X
        # path in this pipeline) and pyzmq/pyrealsense2 (realtime RealSense
        # streaming, unused for a batch clip pipeline). See PROVENANCE.md.
        "pytorch-lightning",
        "pyrender",
        "opencv-python-headless",
        "yacs",
        "scikit-image",
        "einops",
        "timm",
        "dill",
        "pandas",
        "rich",
        "hydra-core",
        "hydra-submitit-launcher",
        "hydra-colorlog",
        "pyrootutils",
        "webdataset",
        "chump",
        "networkx==3.2.1",
        "roma",
        "joblib",
        "seaborn",
        "wandb",
        "appdirs",
        "cython",
        "jsonlines",
        "pytest",
        "xtcocotools",
        "loguru",
        "optree",
        "fvcore",
        "black",
        "pycocotools",
        "tensorboard",
        "huggingface_hub",
    )
    .pip_install(
        # RTMO detection stack (replaces ultralytics -- see G2). No
        # tensorrt-cu12*: rtmlib has no TensorRT branch and G4 skips
        # TensorRT in the gate entirely.
        "onnx",
        "onnxruntime-gpu",
    )
    .pip_install(
        # --no-deps: rtmlib's own requires_dist lists plain "onnxruntime"
        # (CPU), not onnxruntime-gpu. pip installs both into the same
        # onnxruntime/ site-packages directory since they share an import
        # name, and the CPU package's files silently clobber the GPU
        # package's -- CUDAExecutionProvider vanishes from
        # get_available_providers() with no error, only a build-log warning
        # ("multiple onnxruntime packages installed to the same location").
        # numpy/opencv/tqdm are already installed above; nothing else in
        # rtmlib's requires_dist is needed.
        "rtmlib",
        extra_options="--no-deps",
    )
    .pip_install(
        # The published PyPI release of bytetracker (0.3.2) pins lap==0.4.0,
        # whose C extension does not build on Python 3.11 (uses removed
        # CPython internals -- longintrepr.h) or against this image's numpy
        # (AVX-512 FP16 intrinsics gcc here doesn't support). Current
        # upstream `main` already fixed this by switching to lapx (a
        # maintained, prebuilt-wheel drop-in for lap, still MIT) -- install
        # from source instead of the stale PyPI release.
        "git+https://github.com/kadirnar/bytetrack-pip.git",
    )
    .run_commands(
        # --no-build-isolation: needs torch already installed to compile
        # against. --no-deps: its own requirements.txt pulls in stale pins
        # that fight the ones above. CC/CXX: same clang-autodetection issue
        # as lap above -- this image only has gcc/g++.
        "CC=gcc CXX=g++ pip install "
        "'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' "
        "--no-build-isolation --no-deps",
    )
    # Mounted at container start, not baked into the image layer -- editing
    # the adapter doesn't force a rebuild of everything above it.
    .add_local_dir(VENDOR_DIR, remote_path="/app/fast-sam-3d-body")
)


@app.function(image=cv_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights}, timeout=1800)
def verify_cv_stack():
    """Stage 4: does the real CV image actually work end to end?

    Cheaper and more diagnostic than jumping straight to a full clip: proves
    Detectron2 imports (compiled correctly against CUDA_HOME), RTMO actually
    runs on CUDAExecutionProvider (not silently on CPU), and ByteTrack tracks
    across a couple of synthetic frames -- before spending GPU time on a real
    clip.
    """
    import os
    import time

    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch

    print(f"torch {torch.__version__}, cuda available: {torch.cuda.is_available()}")
    assert torch.cuda.is_available(), "CUDA not available in cv_image"

    print("\n--- detectron2 ---")
    import detectron2

    print(f"detectron2 {detectron2.__version__}, compiled ok (import succeeded)")

    print("\n--- onnxruntime providers ---")
    print(f"onnxruntime {ort.__version__}")
    # rtmlib's BaseTool never calls this, so it also happens at import time in
    # tools/rtmo_detector.py -- called again here so this check is accurate
    # even if that import hasn't happened yet in this process.
    ort.preload_dlls()
    print(ort.get_available_providers())
    assert "CUDAExecutionProvider" in ort.get_available_providers(), (
        "onnxruntime-gpu did not register CUDAExecutionProvider -- would silently "
        "fall back to CPU"
    )

    print("\n--- RTMO + ByteTrack on a synthetic frame ---")
    import sys

    sys.path.insert(0, "/app/fast-sam-3d-body")
    from tools.rtmo_detector import RTMODetector

    detector = RTMODetector(device="cuda:0")  # default onnx_model is RTMO-m/body7@640x640
    # Verify the ONNXRuntime session it built is actually on CUDA, not CPU.
    providers = detector.rtmo.session.get_providers()
    print(f"RTMO session providers: {providers}")
    assert providers[0] == "CUDAExecutionProvider", f"RTMO fell back to {providers}"

    frame = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)
    t0 = time.time()
    result = detector.run_human_detection(frame)
    dt = time.time() - t0
    print(f"one frame: {dt * 1000:.1f}ms, boxes={result['boxes'].shape}, "
          f"keypoints={result['keypoints'].shape}")
    assert result["boxes"].shape[1] == 4
    assert result["keypoints"].shape[1:] == (17, 3)

    return {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "ort_providers": ort.get_available_providers(),
        "one_frame_ms": round(dt * 1000, 1),
    }


# Modal's published on-demand rates as of 2026-09 (docs/PRD.md G7: measure,
# don't trust published FPS/cost figures -- this is our own input to that
# math, not a vendor claim about the pipeline itself).
GPU_HOURLY_USD = {"L40S": 1.95, "A10G": 1.10, "T4": 0.59}


@app.function(
    image=cv_image,
    gpu=GPU_TIER,
    volumes={WEIGHTS_DIR: weights, CLIPS_DIR: eval_clips, RESULTS_DIR: results},
    timeout=3600,
)
def run_clip(clip_id: str, fps: float = 15.0, max_seconds: float = 60.0, bbox_thr: float = 0.1):
    """Stage 5: the week-one deliverable. One real clip from evaluation/clips.yaml,
    through RTMO+ByteTrack -> SAM3DBodyEstimator, all detected dancers (docs/PRD.md
    section 5's multi-dancer MVP), saved to the results Volume for stage 6 (export).
    """
    import sys
    import time

    sys.path.insert(0, "/app/fast-sam-3d-body")
    from process_clip import process_clip, save_clip_result

    video_path = f"{CLIPS_DIR}/{clip_id}.mp4"
    checkpoint_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/model.ckpt"
    mhr_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/assets/mhr_model.pt"

    t0 = time.time()
    result = process_clip(
        video_path=video_path,
        checkpoint_path=checkpoint_path,
        mhr_path=mhr_path,
        frames_dir=f"/tmp/{clip_id}_frames",
        fps=fps,
        max_seconds=max_seconds,
        bbox_thr=bbox_thr,
    )
    wall_s = time.time() - t0

    out_path = f"{RESULTS_DIR}/{clip_id}.npz"
    save_clip_result(result, out_path)
    results.commit()

    cost = wall_s / 3600 * GPU_HOURLY_USD.get(GPU_TIER, 0.0)
    print(
        f"\nSAVED {out_path}\n"
        f"wall clock: {wall_s:.1f}s  pipeline-internal: {result['elapsed_s']:.1f}s\n"
        f"peak VRAM: {result['peak_vram_bytes'] / 1e9:.2f} GB\n"
        f"frames: {result['n_frames_ok']}/{result['n_frames_total']} reconstructed\n"
        f"estimated cost at ${GPU_HOURLY_USD.get(GPU_TIER, 0.0)}/hr ({GPU_TIER}): ${cost:.4f}\n"
        "(warm compute only -- excludes cold start, storage, retries, idle billing; see PRD G7)"
    )
    return {
        "wall_s": wall_s,
        "peak_vram_gb": round(result["peak_vram_bytes"] / 1e9, 2),
        "n_frames_ok": result["n_frames_ok"],
        "n_frames_total": result["n_frames_total"],
        "estimated_cost_usd": round(cost, 4),
    }


@app.function(image=base_image, gpu=GPU_TIER, timeout=600)
def verify_gpu():
    """Stage 1: does CUDA actually work on the card we plan to rent?

    Deliberately cheap. Catches a broken image in 30 seconds instead of 20
    minutes into a Detectron2 build.
    """
    import subprocess
    import torch

    print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout)
    print(f"torch          {torch.__version__}")
    print(f"cuda available {torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA not available -- image or GPU request is wrong")
    print(f"cuda version   {torch.version.cuda}")
    print(f"device         {torch.cuda.get_device_name(0)}")
    free, total = torch.cuda.mem_get_info()
    print(f"vram           {free / 1e9:.1f} GB free / {total / 1e9:.1f} GB total")
    # Prove it computes, not just that it enumerates.
    x = torch.randn(2048, 2048, device="cuda")
    print(f"matmul ok      {(x @ x).sum().item():.2f}")
    return {"cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0)}


@app.function(
    image=base_image,
    volumes={WEIGHTS_DIR: weights},
    secrets=HF_SECRET,
    timeout=3600,
)
def download_weights(repo: str = SAM3D_REPO):
    """Stage 2: pull the gated weights into the Volume. No GPU needed.

    This is the real test of the HuggingFace gate. A 401/403 here means the
    request is pending or denied, or the token belongs to a different account --
    not a code bug.
    """
    import os

    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "No HF_TOKEN in the 'huggingface' Modal secret. Create it with:\n"
            "  modal secret create huggingface HF_TOKEN=hf_..."
        )

    target = f"{WEIGHTS_DIR}/{repo.replace('/', '__')}"
    print(f"downloading {repo} -> {target}")
    try:
        path = snapshot_download(
            repo_id=repo,
            local_dir=target,
            token=token,
            max_workers=8,
        )
    except GatedRepoError:
        raise RuntimeError(
            f"{repo} is gated and this token's account has NOT been granted access. "
            f"Check https://huggingface.co/{repo} shows access granted, and that the "
            "token belongs to that same account."
        )
    except RepositoryNotFoundError:
        raise RuntimeError(
            f"{repo} not found -- wrong repo id, or the token lacks read scope."
        )

    weights.commit()

    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print(f"done: {total / 1e9:.2f} GB in {path}")
    return {"repo": repo, "path": path, "gb": round(total / 1e9, 2)}


@app.function(image=base_image, volumes={WEIGHTS_DIR: weights}, timeout=600)
def inspect_weights():
    """Stage 3: what is actually in the Volume, and how big.

    Model repos often ship several checkpoint variants; the PRD's cost and VRAM
    assumptions depend on which one gets loaded, so look before assuming.
    """
    import os

    if not os.path.isdir(WEIGHTS_DIR):
        return {"error": "volume empty -- run download_weights first"}

    found = []
    for root, _, files in os.walk(WEIGHTS_DIR):
        for f in files:
            p = os.path.join(root, f)
            size = os.path.getsize(p)
            if size > 1_000_000:  # skip configs and tokenizer bits
                found.append((os.path.relpath(p, WEIGHTS_DIR), round(size / 1e6, 1)))
    found.sort(key=lambda x: -x[1])
    for name, mb in found[:40]:
        print(f"{mb:10.1f} MB  {name}")
    print(f"\n{len(found)} files over 1MB, {sum(m for _, m in found) / 1000:.2f} GB total")
    return {"files": found[:40], "count": len(found)}


@app.function(image=base_image, volumes={WEIGHTS_DIR: weights}, timeout=600)
def inspect_mhr():
    """Stage 3b: what does the bundled MHR TorchScript file actually contain?

    The PRD assumed MHR's LOD meshes (lod?.fbx, for glTF export) come only from
    a separate ~190 MB GitHub release (assets.zip). A mhr_model.pt is already
    bundled with the SAM 3D Body checkpoint -- this checks whether it is the
    parametric TorchScript model only (per facebookresearch/MHR's own asset
    list: mhr_model.pt is listed separately from lod?.fbx) or whether it
    happens to carry mesh/LOD data too, before deciding assets.zip is still
    required.
    """
    import torch

    path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/assets/mhr_model.pt"
    print(f"loading {path}")
    obj = torch.jit.load(path, map_location="cpu")

    print("\n--- top-level code ---")
    print(obj.code[:4000] if hasattr(obj, "code") else "(no .code)")

    print("\n--- attributes / submodules / buffers ---")
    for name, _ in obj.named_modules():
        if name:
            print(f"module   {name}")
    for name, val in obj.named_buffers():
        shape = tuple(val.shape)
        print(f"buffer   {name:40s} {shape}")
    for name, val in obj.named_parameters():
        shape = tuple(val.shape)
        print(f"param    {name:40s} {shape}")

    print("\n--- methods ---")
    print([m for m in dir(obj) if not m.startswith("_")])

    return {"loaded": True}


# glTF export image (G6). Separate from cv_image on purpose (docs/PRD.md E5):
# pymomentum-gpu's wheels are cp312/cp313 only and pin torch==2.8 -- verified
# against its real PyPI metadata, not assumed from the PRD. Exchanges plain
# arrays (npz) with cv_image's output, never a live Python object.
gltf_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.8.0")
    .pip_install("pymomentum-gpu==0.1.114.post0")
    .pip_install("numpy", "trimesh")
)


@app.function(image=gltf_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights}, timeout=600)
def inspect_pymomentum():
    """Stage 6a: what does pymomentum-gpu's Character / glTF export API
    actually look like, empirically -- the PRD's function name
    (save_gltf_from_skel_states) was renamed upstream to
    save_gltf_with_skel_states in Sep 2025 (facebookresearch/momentum#569),
    which is exactly the kind of drift 'measure, don't trust' exists to catch.
    Also: does loading one of the LOD fbx files from the separate assets.zip
    actually work, and what does the resulting Character expose (joint count/
    names) -- needed to check it lines up with the bundled mhr_model.pt's
    127-joint skeleton before trusting our estimator's skel_state output is
    compatible with it.
    """
    import pymomentum.geometry as pym_geo

    print("pymomentum.geometry members:")
    print([m for m in dir(pym_geo) if not m.startswith("_")])

    print("\nCharacter members:")
    print([m for m in dir(pym_geo.Character) if not m.startswith("_")])

    save_fn = getattr(pym_geo, "save_gltf_with_skel_states", None) or getattr(
        pym_geo, "save_gltf_from_skel_states", None
    )
    print(f"\nsave_gltf function found: {save_fn}")
    if save_fn is not None:
        print(f"docstring: {save_fn.__doc__}")

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    print(f"\nloading Character from {lod_path}")
    load_fn = None
    for candidate in ("load_fbx", "load_fbx_character", "load_gltf", "load_gltf_character"):
        if hasattr(pym_geo, candidate):
            load_fn = getattr(pym_geo, candidate)
            print(f"using loader: {candidate}")
            break
    if load_fn is None:
        return {"error": "no obvious fbx/gltf loader on pymomentum.geometry", "members": dir(pym_geo)}

    character = load_fn(lod_path)
    skeleton = character.skeleton
    print(f"joint count: {skeleton.size}")
    print(f"joint names (first 20): {list(skeleton.joint_names)[:20]}")

    return {
        "save_fn_name": save_fn.__name__ if save_fn else None,
        "load_fn_name": load_fn.__name__,
        "joint_count": skeleton.size,
    }


@app.local_entrypoint()
def main():
    """Run the stages in order, stopping at the first failure."""
    print("\n=== stage 1: GPU ===")
    print(verify_gpu.remote())
    print("\n=== stage 2: gated weights ===")
    print(download_weights.remote())
    print("\n=== stage 3: inspect ===")
    inspect_weights.remote()
