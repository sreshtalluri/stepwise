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

# W4: real user uploads, separate from the versioned eval-clip manifest above --
# api.py writes here directly (Volume access works from any process with a
# Modal token, not just inside a container). run_clip checks this volume
# first, falling back to eval_clips, so evaluation/*.py's existing clip_id-only
# calls (no upload involved) keep working unchanged.
uploads = modal.Volume.from_name("stepwise-uploads", create_if_missing=True)
UPLOADS_DIR = "/uploads"

# Modal resolves every Secret referenced anywhere in the app at load time, so a
# missing 'huggingface' secret would block even functions that never touch it
# (verify_gpu, for one). Degrade gracefully: stage 1 stays runnable before the
# token exists, and download_weights raises its own clear error if it is absent.
try:
    HF_SECRET = [modal.Secret.from_name("huggingface")]
except Exception:  # noqa: BLE001 -- any lookup failure means "not configured yet"
    HF_SECRET = []


def optional_secret(name: str) -> list:
    """`[Secret]` if it exists in this Environment, `[]` if it does not.

    `modal.Secret.from_name` is lazy -- it returns a handle and only fails when
    the deploy resolves it -- so the try/except around HF_SECRET above catches
    nothing, and a missing Secret takes down the whole `modal deploy` including
    every function that never referenced it. `.hydrate()` forces the lookup
    here, where it can be answered with "not configured yet" instead of a
    traceback. This is the difference between "the API cannot be deployed until
    Neon exists" and "the API is deployed and says in /health that Neon does
    not exist yet".
    """
    try:
        s = modal.Secret.from_name(name)
        s.hydrate()
        return [s]
    except Exception:  # noqa: BLE001 -- any lookup failure means "not configured yet"
        print(f"[modal_app] Secret {name!r} not found; continuing without it.")
        return []


# Sentry (observability.py). `SENTRY_DSN_BACKEND` from ~/.stepwise-secrets/sentry.env.
# Absent -> observability.init() is a no-op and errors stay in Modal's one-day
# logs, exactly as before this existed.
SENTRY_SECRET = optional_secret("stepwise-sentry")


def _deployed_sha() -> str | None:
    """The commit being deployed, read from git on the DEPLOYING machine.

    Only meaningful locally: inside a container there is no .git, and the value
    that matters is the one baked into the function spec at `modal deploy`.
    `-dirty` is appended when the tree has uncommitted changes, because a
    release name that claims a commit the code does not match is worse than
    none -- it sends whoever reads the Sentry event to the wrong diff.
    """
    if not modal.is_local():
        return None
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=here, text=True,
                                      stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=here, text=True,
                                        stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001 -- no git, not a checkout: deploy without a release
        return None
    return f"{sha}-dirty" if dirty else sha


# A per-function env var, not an image layer: an `.env()` on the image would
# rebuild a layer on every commit, and a Secret is attached to the function
# spec at deploy with no build at all. It is also how DEPLOYMENT.md §7.1's
# warm-container trap shows up in Sentry: an error whose release is the
# PREVIOUS sha, after a deploy, came from a container that outlived it.
#
# ALWAYS attached, even with no sha: the container re-imports this file, gets
# None from _deployed_sha(), and must still declare the same number of
# dependencies as the deploy did, or every function dies at startup with
# "Function has N dependencies but container got N+1 object ids". Its value
# inside the container is irrelevant -- the object is bound by id at deploy.
_SHA = _deployed_sha()
OBS_SECRETS = SENTRY_SECRET + [modal.Secret.from_dict({"STEPWISE_GIT_SHA": _SHA or ""})]
OBSERVABILITY_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "observability.py")

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
        # W9: the temporal smoothing chain (tools/smoothing.py). PRD section 4
        # says use FilterPy rather than hand-rolling the Kalman filter; it
        # pulls scipy, which the same module uses for quaternion algebra.
        "filterpy",
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
        # Pinned: unpinned (1.30.0 as of 2026-09) requires cuDNN 9 + CUDA 13.
        # This image is pinned to CUDA 12.4 (G3 -- Detectron2 compiles
        # against exactly that toolkit), so the newest onnxruntime-gpu fails
        # at CUDA-session-creation time with "Require cuDNN 9.* and CUDA
        # 13.*" and silently falls back to CPU. 1.20.2 is the last release
        # in the CUDA-12 era.
        "onnxruntime-gpu==1.20.2",
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
    # Last build step on purpose: a new layer here rebuilds nothing above it.
    .pip_install("sentry-sdk>=2.35")
    # Mounted at container start, not baked into the image layer -- editing
    # the adapter doesn't force a rebuild of everything above it.
    .add_local_dir(VENDOR_DIR, remote_path="/app/fast-sam-3d-body")
    .add_local_file(OBSERVABILITY_PY, remote_path="/app/observability.py")
    # W9: the static MHR skeleton (parent indices + joint names) that
    # tools/smoothing.py needs to work in parent-local space. Same file api.py
    # reads; generated once by dump_joint_hierarchy below.
    .add_local_file(
        os.path.join(os.path.dirname(__file__), "mhr_joint_hierarchy.json"),
        remote_path="/app/mhr_joint_hierarchy.json",
    )
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
    # even if that import hasn't happened yet in this process. Guarded: pinned
    # onnxruntime-gpu==1.20.2 predates preload_dlls (added in 1.21).
    if hasattr(ort, "preload_dlls"):
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
    volumes={WEIGHTS_DIR: weights, CLIPS_DIR: eval_clips, UPLOADS_DIR: uploads, RESULTS_DIR: results},
    secrets=OBS_SECRETS,
    timeout=3600,
)
def run_clip(clip_id: str, fps: float = 15.0, max_seconds: float = 60.0, bbox_thr: float = 0.1,
             job_id: str | None = None, retry_count: int = 0):
    """Stage 5: the week-one deliverable. One real clip -- a real user upload
    (services/motion-api/api.py writes it to the `stepwise-uploads` Volume) or
    an evaluation/clips.yaml clip (the `stepwise-eval` Volume, checked as a
    fallback so evaluation/*.py's existing calls are unaffected) -- through
    RTMO+ByteTrack -> SAM3DBodyEstimator, every confidently-tracked dancer up
    to the 6-dancer cap (docs/PRD.md section 5's revised multi-dancer MVP).

    W8: emits job-status.schema.json-compliant progress documents to the
    results Volume as `{job_id}.job-status.json`, one write per real pipeline
    stage transition. W4: api.py's HTTP layer polls/serves this file, and this
    function itself now dispatches export_clip_gltf.remote() once reconstruction
    succeeds -- so the whole run_clip -> export_clip_gltf order (spec item 2)
    happens inside one spawned worker, and "succeeded" is only written once a
    GLB actually exists for every dancer, not right after reconstruction.
    """
    import json
    import os
    import sys
    import time

    sys.path.insert(0, "/app/fast-sam-3d-body")
    from tools.process_clip import process_clip, save_clip_result
    sys.path.insert(0, "/app")
    import observability

    job_id = job_id or f"job_{clip_id}_{int(time.time())}"
    tags = {"clip_id": clip_id, "job_id": job_id, "retry_count": retry_count}
    status_path = f"{RESULTS_DIR}/{job_id}.job-status.json"

    def write_status(state: str, stage_message: str, progress, error=None):
        doc = {
            "schema_version": "1.0.0",
            "job_id": job_id,
            "state": state,
            "stage_message": stage_message,
            "progress": progress,
            "error": error,
            "retry_count": retry_count,
        }
        with open(status_path, "w") as f:
            json.dump(doc, f)
        results.commit()
        print(f"[job-status] {state} {progress if progress is not None else '-'}  {stage_message}")

    def on_progress(stage: str, message: str, progress) -> None:
        write_status("refused" if stage == "refused" else "processing", message, progress)

    write_status("queued", "", None)

    upload_path = f"{UPLOADS_DIR}/{clip_id}.mp4"
    if not os.path.exists(upload_path):
        # Real bug caught by an actual end-to-end run (see docs/GATE-REPORT.md
        # W4 addendum): a container started immediately after api.py's
        # batch_upload().commit() can win a race against that commit's
        # propagation and see a stale mount, silently falling through to the
        # eval-clip path and failing with a confusing "file not found in the
        # wrong volume" error. One reload() + recheck before falling back to
        # the eval volume is the cheap fix; this is a Volume, not a queue --
        # there is no delivery guarantee beyond "eventually consistent".
        uploads.reload()
    video_path = upload_path if os.path.exists(upload_path) else f"{CLIPS_DIR}/{clip_id}.mp4"
    checkpoint_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/model.ckpt"
    mhr_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/assets/mhr_model.pt"

    # Beats are CPU-only and independent of reconstruction, so they run beside
    # it rather than after it: spawned here, collected below, and the whole cost
    # disappears inside the ~90 s the GPU is busy. Sequenced instead, a cold CPU
    # container start would be pure added wall time on every job.
    beats_call = propose_counts.spawn(clip_id)

    t0 = time.time()
    try:
        result = process_clip(
            video_path=video_path,
            checkpoint_path=checkpoint_path,
            mhr_path=mhr_path,
            frames_dir=f"/tmp/{clip_id}_frames",
            fps=fps,
            max_seconds=max_seconds,
            bbox_thr=bbox_thr,
            on_progress=on_progress,
        )
    except Exception as e:  # noqa: BLE001 -- surface as a job-status failure, not a bare crash
        write_status(
            "failed", "",
            None,
            error={"code": "pipeline_error", "message": str(e), "retryable": True},
        )
        observability.capture(e, "run_clip", stage="reconstruct", **tags)
        raise
    wall_s = time.time() - t0

    if result.get("refused"):
        # job-status "state" has no dedicated refused value (job-status.schema.json
        # only has queued/processing/succeeded/failed) -- a refusal IS a completed,
        # non-retryable failure from the caller's point of view, not a crash.
        write_status(
            "failed", "",
            None,
            error={
                "code": "too_many_dancers",
                "message": result["refusal_message"],
                "retryable": False,
            },
        )
        print(f"REFUSED: {result['refusal_message']}")
        return {
            "refused": True,
            "n_confident_dancers": result["n_confident_dancers"],
        }

    out_path = f"{RESULTS_DIR}/{clip_id}.npz"
    save_clip_result(result, out_path)
    results.commit()

    cost = wall_s / 3600 * GPU_HOURLY_USD.get(GPU_TIER, 0.0)
    n_dancers = len(result["confident_track_ids"])

    # Real, measured numbers for MotionResult.model_report.measured_performance
    # (motion-result.schema.json) -- api.py reads this rather than re-deriving
    # fps/vram/cost from the npz itself.
    perf = {
        "fps": round(result["n_frames_total"] / result["elapsed_s"], 3) if result["elapsed_s"] > 0 else 0.0,
        "peak_vram_mb": round(result["peak_vram_bytes"] / 1e6, 1),
        "cost_usd": round(cost, 4),
    }
    with open(f"{RESULTS_DIR}/{clip_id}.performance.json", "w") as f:
        json.dump(perf, f)

    # Same hand-off pattern as performance.json above: this stage has the video,
    # the export stage has the timeline, and a small JSON in the results Volume
    # is how they already talk. Absent file == no proposal, which the reader
    # treats as normal. Listed in retention.clip_artifact_paths so a removal
    # request takes it with everything else.
    try:
        beats = beats_call.get()
    except Exception as e:  # noqa: BLE001 -- a beat failure is never a job failure
        print(f"[beats] {clip_id}: proposal stage failed ({type(e).__name__}: {e})")
        # Warning, not error: the lesson still ships, just without proposed
        # counts. Reported anyway -- a beat stage that fails on every clip
        # would otherwise look exactly like clips with no audio.
        observability.capture(e, "run_clip", level="warning", stage="beats", **tags)
        beats = None
    if beats:
        with open(f"{RESULTS_DIR}/{clip_id}.beats.json", "w") as f:
            json.dump(beats, f)

    print(
        f"\nSAVED {out_path}\n"
        f"wall clock: {wall_s:.1f}s  pipeline-internal: {result['elapsed_s']:.1f}s\n"
        f"peak VRAM: {result['peak_vram_bytes'] / 1e9:.2f} GB\n"
        f"dancers reconstructed: {n_dancers}\n"
        f"frames: {result['n_frames_ok']}/{result['n_frames_total']} reconstructed\n"
        f"estimated cost at ${GPU_HOURLY_USD.get(GPU_TIER, 0.0)}/hr ({GPU_TIER}): ${cost:.4f}\n"
        "(warm compute only -- excludes cold start, storage, retries, idle billing; see PRD G7. "
        "Measured for THIS clip's dancer count -- do not extrapolate the solo-01 gate numbers.)"
    )

    # W4 spec item 2: dispatch export ONLY after run_clip succeeds, in order.
    # Blocking .remote() here is fine -- this whole function was already
    # dispatched off the HTTP request via .spawn() in api.py, so blocking
    # inside this worker does not block any client. "succeeded" is written
    # only once the GLB(s) genuinely exist, not right after reconstruction --
    # a client polling job status should never see "succeeded" for a job
    # whose MotionResult/assets aren't actually fetchable yet.
    write_status("processing", "Building the 3D body file", 0.97)
    try:
        export_result = export_clip_gltf.remote(clip_id, job_id)
    except Exception as e:  # noqa: BLE001 -- a real crash in the export stage, not a pipeline_error
        write_status(
            "failed", "", None,
            error={"code": "export_error", "message": str(e), "retryable": True},
        )
        observability.capture(e, "run_clip", stage="export", **tags)
        raise

    write_status("succeeded", "", 1.0)
    return {
        "refused": False,
        "wall_s": wall_s,
        "peak_vram_gb": round(result["peak_vram_bytes"] / 1e9, 2),
        "n_dancers": n_dancers,
        "n_frames_ok": result["n_frames_ok"],
        "n_frames_total": result["n_frames_total"],
        "estimated_cost_usd": round(cost, 4),
        "export": export_result,
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
GLTF_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "tools")

gltf_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.8.0")
    .pip_install("pymomentum-gpu==0.1.114.post0")
    # pygltflib: post-export GLB surgery, now for TWO independent reasons that
    # both land on the same dependency.
    #   * W10's region_mask.py splits the single skinned mesh
    #     save_gltf_from_skel_states writes into named region_<id> sub-meshes
    #     (docs/OPEN-DECISIONS.md E3).
    #   * export-quality's `_rewrite_interpolation_linear` fixes up the sampler
    #     interpolation mode, because pymomentum has no interpolation knob
    #     (verified empirically against this exact pin).
    # Plain glTF JSON/buffer manipulation in both cases -- no pymomentum or
    # trimesh API needed for either.
    .pip_install("numpy", "trimesh", "pygltflib")
    # boto3, in its OWN layer on purpose: appending it here leaves every layer
    # above -- including the pymomentum pin that took seven environment bugs to
    # get green (docs/GATE-REPORT.md G3) -- cached and untouched. It is pure
    # Python over urllib3 and shares no transitive dependency with torch,
    # numpy or pymomentum, which is why adding it to a pinned image is
    # acceptable at all. infrastructure.md §5 names the escape hatch if a
    # pinned image ever does go red for a reason like this: a tiny CPU sidecar
    # function invoked with .spawn(). Not needed; recorded in DEPLOYMENT.md.
    .pip_install("boto3")
    # Mounted at container start, same pattern as cv_image's VENDOR_DIR --
    # editing region_mask.py doesn't force a rebuild of the layers above.
    .add_local_dir(GLTF_TOOLS_DIR, remote_path="/app/motion-api-tools")
    # R2 publication happens here, at the end of export, because this is the
    # first moment every delivered byte of a lesson exists (infrastructure.md
    # migration step 5). Mounted alongside the assembly for the same reason.
    .add_local_file(os.path.join(os.path.dirname(__file__), "storage.py"),
                    "/app/storage.py")
    # The MotionResult assembly, so the exporter can materialise the contract
    # document once here instead of api.py rebuilding it from the npz on every
    # single request. motion_result.py reads mhr_joint_hierarchy.json from its
    # own directory, so they land in /app together. Mounted, not baked: editing
    # the assembly must not rebuild the pymomentum layer above it.
    #
    # grounding.py joins them (second integration pass): the merged assembly
    # does the real floor solve and the real intrinsics estimate, which the
    # w4-era copy this branch lifted did not. It is pure numpy -- no torch, no
    # web framework -- so it costs this image nothing.
    .add_local_file(os.path.join(os.path.dirname(__file__), "motion_result.py"),
                    "/app/motion_result.py")
    .add_local_file(os.path.join(os.path.dirname(__file__), "mhr_joint_hierarchy.json"),
                    "/app/mhr_joint_hierarchy.json")
    .add_local_file(os.path.join(os.path.dirname(__file__), "grounding.py"),
                    "/app/grounding.py")
    # world-placement (third integration pass, OPEN-DECISIONS E6): motion_result
    # now imports world_placement_probe for the real per-frame camera-space
    # placement, and world_placement_probe in turn imports skeleton_constraints
    # (for the rigid-body step) and grounding (already mounted above) -- both
    # resolve via the same flat /app on sys.path this image already relies on
    # for motion_result's plain `from grounding import ...` to work, so no
    # import-path changes are needed in either module, only these two mounts.
    .add_local_file(os.path.join(os.path.dirname(__file__), "world_placement_probe.py"),
                    "/app/world_placement_probe.py")
    .add_local_file(os.path.join(os.path.dirname(__file__),
                                  "vendor/fast-sam-3d-body/tools/skeleton_constraints.py"),
                    "/app/skeleton_constraints.py")
)

BEAT_DETECT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "packages", "beat-detect", "python", "beat_detect",
)

# W11's beat proposal. Its own image, CPU-only, and NOT a layer on cv_image --
# that is a deliberate call with a measured cost behind it, not caution.
#
# librosa pulls numba, and numba pins numpy hard. cv_image's numpy is already
# load-bearing in three directions at once: detectron2 compiles a CUDA
# extension against it, bytetrack's lapx replacement exists because the stock
# build broke on this image's numpy AVX-512 intrinsics, and onnxruntime-gpu is
# pinned to 1.20.2 for the CUDA-12.4 era. Adding a pip that can move numpy puts
# all three at risk for a 5-second audio job. Worse, it lands ABOVE the
# detectron2 compile in the layer stack, so every rebuild pays for it:
# docs/INTEGRATION.md §5 measured that at ~13 minutes.
#
# gltf_image was the other candidate and is a non-starter for a simpler reason:
# it has neither ffmpeg nor the source video mounted.
#
# So: debian_slim + ffmpeg + librosa, no GPU. A 20 s clip is seconds of CPU,
# which at Modal's CPU rate rounds to nothing against the $0.076 the L40S pass
# costs. It rebuilds on its own and can break nothing else.
beat_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")  # propose_grid shells out to it to pull the audio track
    .pip_install("librosa>=0.10", "numpy>=1.26", "soundfile>=0.12")
    .add_local_dir(BEAT_DETECT_DIR, remote_path="/app/beat_detect")
)


@app.function(image=beat_image, volumes={CLIPS_DIR: eval_clips, UPLOADS_DIR: uploads}, timeout=600)
def propose_counts(clip_id: str) -> dict | None:
    """Propose a count grid from the clip's audio. A PROPOSAL, never a decision.

    Returns `beat_detect.ProposedGrid` as a dict, or None when there is nothing
    to propose from. Returning None is a normal outcome -- a clip with no audio
    track, a silent clip, or a tracker that found fewer than two beats -- and
    the caller must treat it as such: the lesson still works, the learner sets
    counts by hand, which they can always do anyway.

    `count_total` is deliberately NOT computed here even though the duration is
    to hand: the contract's grid is sized against `sample_times_s`, which only
    exists after reconstruction. motion_result._proposed_counts does it.
    """
    import os
    import sys
    from dataclasses import asdict

    sys.path.insert(0, "/app")
    from beat_detect import propose_grid

    upload_path = f"{UPLOADS_DIR}/{clip_id}.mp4"
    if not os.path.exists(upload_path):
        uploads.reload()  # same eventual-consistency guard run_clip uses
    video_path = upload_path if os.path.exists(upload_path) else f"{CLIPS_DIR}/{clip_id}.mp4"
    if not os.path.exists(video_path):
        print(f"[beats] {clip_id}: no video to read")
        return None

    try:
        grid = asdict(propose_grid(video_path))
    except Exception as e:  # noqa: BLE001 -- a missing audio track raises from ffmpeg
        # Never fail the job over a proposal. A lesson with hand-set counts is
        # the product; a lesson that did not get made is not.
        print(f"[beats] {clip_id}: no proposal ({type(e).__name__}: {e})")
        return None
    if not grid["seconds_per_count"] > 0:
        print(f"[beats] {clip_id}: no proposal (degenerate spacing)")
        return None
    print(f"[beats] {clip_id}: {grid['bpm']:.1f} BPM, {grid['seconds_per_count']:.4f} s/count, "
          f"count 1 at {grid['count_one_s']:.3f}s, confidence {grid['confidence']:.2f}"
          + (f", warnings: {grid['warnings']}" if grid["warnings"] else ""))
    return grid


# CPU-only image for the retention sweeper: it moves no arrays, it only lists
# and deletes Volume paths, so it has no business loading torch. boto3 joins it
# because a lesson's bytes now live in two places, and a sweeper that forgets
# one of them is a privacy leak rather than a storage leak
# (docs/research/rights-and-privacy.md §1).
sweeper_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("boto3", "sentry-sdk>=2.35")
    .add_local_file(os.path.join(os.path.dirname(__file__), "retention.py"),
                    "/app/retention.py")
    .add_local_file(os.path.join(os.path.dirname(__file__), "storage.py"),
                    "/app/storage.py")
    .add_local_file(OBSERVABILITY_PY, "/app/observability.py")
)

# R2 credentials. Absent -> every caller keeps its Volume path and says so
# (storage.enabled()), rather than the app failing to load.
R2_SECRET = optional_secret("stepwise-r2")

# The database. Does not exist yet (Neon is being provisioned in parallel);
# until it does, `STEPWISE_JOB_BACKEND` stays unset and jobstore.py serves job
# state from the results Volume exactly as before. Creating the Secret and
# setting the variable is the whole cutover -- see docs/DEPLOYMENT.md.
DB_SECRET = optional_secret("stepwise-db")

# STEPWISE_ORIGIN_KEY: with it, the API answers only the Cloudflare Worker and
# trusts the learner IP that Worker forwards (ratelimit.origin_key_ok). Absent
# -> the API is open to anyone, as before, and per-IP limits use the socket.
ORIGIN_SECRET = optional_secret("stepwise-origin")


# glTF sampler interpolation, fixed up after pymomentum writes the file.
#
# pymomentum 0.1.114.post0 emits `STEP` on every animation sampler and offers
# no way to ask for anything else. That is not a guess: every export path it
# exposes was tried against the real MHR skeleton and all three produce STEP --
# `Character.save_gltf_from_skel_states` plain, the same call with a
# `FileSaveOptions`, and the lower-level `GltfBuilder.add_skeleton_states`.
# `FileSaveOptions` has nine fields (blend_shapes, collisions,
# coord_system_info, extensions, fbx_namespace, gltf_file_format, locators,
# mesh, permissive) and none concerns interpolation, and every plausible
# keyword (`interpolation=`, `interp=`, `linear=`, ...) is rejected by the
# pybind11 signature. So a post-export rewrite is the only available fix, and
# it follows the precedent already set for GLB post-processing with pygltflib.
#
# STEP means no interpolation at all: the pose snaps to each keyframe and holds
# it until the next one. Measured on the real solo-01 export, sampling 4x denser
# than the 15 fps keyframes: 75.8% of rendered samples are a dead freeze and the
# body then teleports up to 629 mm in a single sample. That is the "tracking the
# movements properly, but not crisp like human movement" complaint, exactly.
#
# LINEAR, not CUBICSPLINE. Measured by holding out every other real keyframe from
# the solo-01 export and reconstructing it (world joint error, mm):
#
#     STEP          median 74.58   p90 233.51   max 629.10
#     LINEAR        median 47.48   p90 131.62   max 382.88
#     CUBICSPLINE   median 42.01   p90 122.53   max 368.23
#
# CUBICSPLINE buys 11% on the median over LINEAR and costs 3x the animation
# bytes (it stores an in- and out-tangent per keyframe), makes bone length
# slightly WORSE between keyframes (18.84 mm worst vs LINEAR's 18.05 mm), and
# -- the deciding argument -- those tangents are fabricated. Nothing in the
# reconstruction measures velocity; a Catmull-Rom tangent is invented and then
# rendered indistinguishably from measured data, which is precisely what
# DESIGN.md §7h forbids. LINEAR adds no numbers at all: on rotations the glTF
# spec defines it as slerp, and every value in the file is still one the
# pipeline actually produced.
#
# This is pure metadata. The binary chunk is byte-identical across the rewrite
# (verified: same length, same bytes, max keyframe-value difference exactly
# 0.0), so bone lengths at every keyframe are untouched and the bone-constraint
# work's CV survives exactly.
#
# Known, measured cost of LINEAR, disclosed rather than hidden: pymomentum
# carries part of some joints' bone DIRECTION in the translation channel rather
# than the parent's rotation (l_index1's local offset swings 79 degrees between
# adjacent keyframes while its length stays constant to 6 decimal places).
# Lerping a direction takes the chord, so those bones shorten transiently
# BETWEEN keyframes -- median 0.00006 mm, p90 0.44 mm, but up to 18 mm (23% of
# its length) on a finger. It is exact again at every keyframe. glTF has no
# "slerp the translation" mode, so the only real fix is re-deriving the local
# decomposition so bone direction lives in the rotation channel; that is a
# change to the export itself, not to this attribute, and it is recorded in
# docs/OPEN-DECISIONS.md rather than guessed at here.
GLTF_INTERPOLATION = "LINEAR"


def _rewrite_interpolation_linear(glb_path: str) -> dict:
    """Rewrite every animation sampler's interpolation mode in place.

    Verifies its own work before returning: a silently-failed rewrite would
    ship a snapping animation that looks like a viewer bug, and a corrupted
    binary chunk would ship an invisible model. Both are checked, not assumed.
    """
    import numpy as np
    import pygltflib

    gltf = pygltflib.GLTF2().load(glb_path)
    before = gltf.binary_blob()

    n_rewritten = 0
    n_samplers = 0
    for anim in gltf.animations:
        for sampler in anim.samplers:
            n_samplers += 1
            if sampler.interpolation != GLTF_INTERPOLATION:
                sampler.interpolation = GLTF_INTERPOLATION
                n_rewritten += 1
    gltf.save(glb_path)

    after = pygltflib.GLTF2().load(glb_path)
    blob = after.binary_blob()
    if blob != before:
        raise ValueError(
            f"{glb_path}: the interpolation rewrite changed the binary chunk "
            f"({len(before)} -> {len(blob)} bytes). It must be metadata-only -- "
            "refusing to ship an animation whose keyframe data was altered."
        )
    modes = {s.interpolation for a in after.animations for s in a.samplers}
    if modes != {GLTF_INTERPOLATION}:
        raise ValueError(
            f"{glb_path}: interpolation is {modes} after the rewrite, expected "
            f"{{'{GLTF_INTERPOLATION}'}}."
        )
    if not np.all(np.isfinite(np.frombuffer(blob, dtype=np.float32))):
        raise ValueError(
            f"{glb_path}: non-finite values in the binary chunk after rewrite. "
            "Refusing to write a GLB that would render as nothing."
        )
    return {"n_samplers": n_samplers, "n_rewritten": n_rewritten, "interpolation": GLTF_INTERPOLATION}


@app.function(image=gltf_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights}, timeout=600)
def inspect_pymomentum():
    """Stage 6a: what does pymomentum-gpu's Character / glTF export API
    actually look like, empirically. A quick web check suggested the PRD's
    function name (save_gltf_from_skel_states) was renamed upstream to
    save_gltf_with_skel_states in Sep 2025 (facebookresearch/momentum#569) --
    that PR exists, but this pinned release (0.1.114.post0) still ships the
    original name, so the PRD was actually right and the web search that
    flagged a rename was checking a newer unreleased state. Recorded here
    because "measure, don't trust" cuts both ways: don't trust a claimed fix
    either, without checking what's actually installed.
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

    # Both save_gltf_from_skel_states and load_fbx showed up in
    # dir(pym_geo.Character), not dir(pym_geo) -- they are attached to the
    # Character class (pybind11 def_static bindings: callable without an
    # instance, e.g. Character.load_fbx(path), but still class-scoped, not
    # module-level functions). The Sep 2025 rename to
    # save_gltf_with_skel_states (facebookresearch/momentum#569) evidently
    # has not shipped in pymomentum-gpu==0.1.114.post0 -- the PRD's original
    # name is the one actually installed.
    save_fn = getattr(pym_geo.Character, "save_gltf_with_skel_states", None) or getattr(
        pym_geo.Character, "save_gltf_from_skel_states", None
    )
    print(f"\nsave_gltf function found on Character: {save_fn}")
    if save_fn is not None:
        print(f"docstring: {save_fn.__doc__}")

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    print(f"\nloading Character from {lod_path} via Character.load_fbx")
    character = pym_geo.Character.load_fbx(lod_path)
    skeleton = character.skeleton
    print(f"joint count: {skeleton.size}")
    print(f"joint names (first 20): {list(skeleton.joint_names)[:20]}")
    has_mesh_attr = character.has_mesh
    print(f"has_mesh: {has_mesh_attr() if callable(has_mesh_attr) else has_mesh_attr}")

    return {
        "save_fn_name": save_fn.__name__ if save_fn else None,
        "joint_count": skeleton.size,
        "joint_names": list(skeleton.joint_names),
    }


@app.function(image=gltf_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights, RESULTS_DIR: results}, timeout=600)
def export_neutral_pose_smoke_test():
    """Stage 6b: does the export MECHANISM work at all -- Character loaded
    from a LOD fbx, skel_state from the bundled MHR TorchScript model, and
    Character.save_gltf_from_skel_states -- independent of whether it is
    driven by real per-frame video reconstruction yet.

    Deliberately narrow: calls the bundled mhr_model.pt's own forward()
    directly with a neutral (all-zero) pose, not through SAM3DBodyEstimator.
    Kept as-is (still useful as a cheap mechanism-only smoke test that doesn't
    need a real clip run first) now that the neutral-pose gap itself is closed
    -- see export_clip_gltf below, which drives this same mechanism from real
    per-frame `skel_state` (sam_3d_body/models/heads/mhr_head.py's
    _mhr_forward_core now returns it directly, W8, docs/GATE-REPORT.md G6).
    """
    import numpy as np
    import pymomentum.geometry as pym_geo
    import torch

    mhr_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/assets/mhr_model.pt"
    print(f"loading {mhr_path}")
    mhr = torch.jit.load(mhr_path, map_location="cpu")
    mhr.eval()

    # Shapes from the buffer inspection in inspect_mhr: blend_shape.shape_vectors
    # is (45, 18439, 3) -> 45 shape params; face_expressions_model.shape_vectors
    # is (72, ...) -> 72 expression params; parameter_transform.parameter_transform
    # is (889, 249) -> 249-dim model_parameters (pose+scale).
    # model_params is internally concatenated with a 45-dim zeros vector
    # (matching shape_params) before hitting a 249-dim parameter_transform --
    # confirmed empirically: passing 249 here raised "einsum(): subscript n
    # has size 294 ... does not broadcast with previously seen size 249"
    # (249 + 45 = 294). So model_params itself is 204-dim, not 249.
    shape_params = torch.zeros(1, 45)
    model_params = torch.zeros(1, 204)
    expr_params = torch.zeros(1, 72)
    with torch.no_grad():
        verts, skel_state = mhr(shape_params, model_params, expr_params, False)
    print(f"verts: {tuple(verts.shape)}, skel_state: {tuple(skel_state.shape)}")

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    character = pym_geo.Character.load_fbx(lod_path)
    print(f"character joints: {character.skeleton.size}")

    # save_gltf_from_skel_states signature (confirmed empirically via
    # inspect_pymomentum): (path, character, fps, skel_states: (F,J,8) f32,
    # markers=None, options=None). One repeated frame -> a valid, if static,
    # animation clip, sufficient to prove the mechanism.
    n_frames = 2
    # skel_state is (1, 127, 8) -- batch dim first, from a single forward()
    # call. save_gltf_from_skel_states wants (F, J, 8), so drop the batch dim
    # before repeating across frames, not after (repeating with it still
    # there gives (F, 1, 127, 8), a shape save_gltf_from_skel_states does not
    # expect).
    single_frame = skel_state[0].numpy().astype(np.float32)  # (127, 8)
    skel_states_np = np.repeat(single_frame[None, :, :], n_frames, axis=0)  # (F, 127, 8)
    print(f"skel_states for export: {skel_states_np.shape}, dtype={skel_states_np.dtype}")

    out_path = f"{RESULTS_DIR}/neutral_pose_smoke_test.glb"
    pym_geo.Character.save_gltf_from_skel_states(
        out_path, character, 15.0, skel_states_np
    )
    results.commit()

    import os

    size_bytes = os.path.getsize(out_path)
    print(f"SAVED {out_path}, {size_bytes} bytes")
    return {"out_path": out_path, "size_bytes": size_bytes}


@app.function(image=gltf_image, volumes={WEIGHTS_DIR: weights, RESULTS_DIR: results}, timeout=300)
def dump_joint_hierarchy():
    """W4: one-off introspection, not a per-request call. `joint_hierarchy` is
    "fixed for the life of schema v1.0.0" per motion-result.schema.json, so it
    is generated here once and saved as a static file
    (services/motion-api/mhr_joint_hierarchy.json) that api.py loads from disk
    -- the lightweight FastAPI service should not need pymomentum/CUDA installed
    just to answer a status/result poll. No GPU requested: skeleton
    introspection is CPU-only (Character/Skeleton are plain data, not a model
    forward pass).
    """
    import numpy as np
    import pymomentum.geometry as pym_geo

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    character = pym_geo.Character.load_fbx(lod_path)
    skeleton = character.skeleton
    names = list(skeleton.joint_names)
    parents = list(skeleton.joint_parents)  # -1 for root, per pymomentum convention
    # Rest pose: skeleton exposes offsets (translation) and pre-rotation per
    # joint in its own attribute names -- introspect rather than guess.
    print("skeleton attrs:", [a for a in dir(skeleton) if not a.startswith("_")])
    rest_translations = np.asarray(skeleton.offsets) if hasattr(skeleton, "offsets") else None
    rest_rotations = None
    for attr in ("pre_rotations", "rest_rotations", "joint_rotations"):
        if hasattr(skeleton, attr):
            rest_rotations = np.asarray(getattr(skeleton, attr))
            print(f"rest rotation source: {attr}, shape {rest_rotations.shape}")
            break
    print(f"joints: {len(names)}, parents sample: {parents[:10]}")
    if rest_translations is not None:
        print(f"rest_translations shape: {rest_translations.shape}")
    out = {
        "names": names,
        "parents": parents,
        "rest_translations": rest_translations.tolist() if rest_translations is not None else None,
        "rest_rotations": rest_rotations.tolist() if rest_rotations is not None else None,
    }
    import json
    with open(f"{RESULTS_DIR}/mhr_skeleton_raw.json", "w") as f:
        json.dump(out, f)
    results.commit()
    return out


def _mhr_shape_basis(mhr_path):
    """MHR's own blend-shape pathway, read straight out of the bundled
    TorchScript buffers: (neutral_verts (18439,3), shape_vectors (45,18439,3)).

    rest_verts(shape) = base_shape + einsum(shape, shape_vectors) -- verified on
    real hardware against the model's own forward pass (mhr(shape, 0, 0)):
    max abs difference 3.8e-5 cm, so the buffers ARE the forward's shape path
    and no 204-dim model_parameters guess is needed. Also verified: shape
    changes only the mesh, never the skeleton (rest joint positions and the
    skel_state scale column are bit-identical at shape=0 and shape=median), so
    baking shape into the rest mesh cannot conflict with the per-frame
    skel_state animation -- they are exactly MHR's own two stages.
    """
    import numpy as np
    import torch

    bufs = dict(torch.jit.load(mhr_path, map_location="cpu").named_buffers())
    base = bufs["character_torch.blend_shape.base_shape"].numpy().astype(np.float64)
    vecs = bufs["character_torch.blend_shape.shape_vectors"].numpy().astype(np.float64)
    return base, vecs


def _nearest_vertex_map(src, dst, block=4096):
    """For every src vertex, the index of the nearest dst vertex (chunked, CPU).

    Needed because the shipped LOD meshes are decimated (lod3 = 4899 verts) while
    the shape basis is defined on MHR's full-res 18439-vert mesh. Measured on the
    real assets: lod3's vertices sit a mean 0.297 cm (max 1.79) off the full-res
    surface in the same rest pose and units, i.e. lod3 is a resampling of the
    same body, so sampling the (smooth, low-frequency) shape displacement field
    at the nearest full-res vertex is well posed.
    ponytail: 1-NN sampling, not barycentric projection onto the nearest
    triangle. Upgrade only if a measurement shows the difference matters -- the
    displacement field varies far more slowly than the 3 mm sampling offset.
    """
    import numpy as np

    src = np.ascontiguousarray(src, dtype=np.float32)
    dst = np.ascontiguousarray(dst, dtype=np.float32)
    src_sq = (src ** 2).sum(1)[:, None]
    best = np.full(len(src), np.inf, dtype=np.float32)
    idx = np.zeros(len(src), dtype=np.int64)
    for i in range(0, len(dst), block):
        blk = dst[i:i + block]
        d2 = src_sq + (blk ** 2).sum(1)[None, :] - 2.0 * (src @ blk.T)
        m = d2.argmin(1)
        dm = d2[np.arange(len(src)), m]
        upd = dm < best
        best[upd] = dm[upd]
        idx[upd] = i + m[upd]
    return idx, np.sqrt(np.maximum(best, 0.0))


def _character_with_shape(character, shape_vec, shape_vectors, lod_to_mhr):
    """The same character with this dancer's estimated body shape baked into its
    rest mesh (skeleton, skin weights, UVs and topology untouched).

    pymomentum has no "apply blend-shape coefficients to a Character" call:
    Character.with_blend_shape() attaches a basis for the *solver* to drive
    through model parameters, and Character.save_gltf_from_skel_states() takes
    skel_states only -- there is no parameter channel to carry shape into the
    export. Baking the displacement into the rest mesh is the supported route:
    LBS is applied to the rest vertices, so a shaped rest mesh + the estimator's
    skel_state reproduces MHR's own (shape -> rest verts -> LBS) pipeline.
    """
    import numpy as np
    import pymomentum.geometry as pym_geo

    mesh = character.mesh
    rest = np.asarray(mesh.vertices, dtype=np.float64)
    delta_full = np.einsum("k,kvj->vj", np.asarray(shape_vec, dtype=np.float64), shape_vectors)
    shaped = rest + delta_full[lod_to_mhr]
    if not np.all(np.isfinite(shaped)):
        raise ValueError("non-finite shaped rest vertices; refusing to export a broken mesh")

    def _opt(attr):
        val = np.asarray(getattr(mesh, attr))
        return val if val.size else None

    shaped_mesh = pym_geo.Mesh(
        vertices=shaped.astype(np.float32),
        faces=np.asarray(mesh.faces),
        colors=_opt("colors"),
        confidence=_opt("confidence"),
        texcoords=_opt("texcoords"),
        texcoord_faces=_opt("texcoord_faces"),
        poly_faces=mesh.poly_faces,
        poly_face_sizes=mesh.poly_face_sizes,
        poly_texcoord_faces=mesh.poly_texcoord_faces,
    ).with_updated_normals()  # normals must follow the new surface, not the mean body
    return character.with_mesh_and_skin_weights(shaped_mesh, character.skin_weights), shaped - rest


@app.function(image=gltf_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights}, timeout=600)
def inspect_mhr_region_mapping():
    """W10 diagnostic (not required by export_clip_gltf, which resolves this
    itself): prints the real `lod3.fbx` skeleton's joint names and whether
    region_mask.resolve_canonical_joints can match all 18 REGIONS bones
    against them -- the single biggest unverified assumption this pass makes
    (see the W10 report). Run this BEFORE trusting export_clip_gltf's output
    on a real clip; if it raises RegionMappingError, read the message (it
    names exactly which canonical joints didn't match) and extend
    tools/region_mask.py's _CATEGORY_MATCHERS rather than guessing.

    `character.skeleton`'s parent-index attribute name was never confirmed in
    this pass either (only `.joint_names`/`.size` were, per inspect_pymomentum
    above) -- this tries the plausible attribute names and reports which one
    worked, rather than assuming.
    """
    import sys

    import pymomentum.geometry as pym_geo

    sys.path.insert(0, "/app/motion-api-tools")
    from region_mask import resolve_canonical_joints

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    character = pym_geo.Character.load_fbx(lod_path)
    skeleton = character.skeleton
    joint_names = list(skeleton.joint_names)

    parent_indices = None
    for attr in ("joint_parents", "parents", "parent", "parent_indices"):
        if hasattr(skeleton, attr):
            candidate = list(getattr(skeleton, attr))
            if len(candidate) == len(joint_names):
                parent_indices = candidate
                print(f"parent indices via skeleton.{attr}")
                break
    if parent_indices is None:
        raise RuntimeError(
            f"couldn't find a parent-index attribute on Skeleton (tried joint_parents/parents/"
            f"parent/parent_indices); dir(skeleton)={[a for a in dir(skeleton) if not a.startswith('_')]}"
        )

    print(f"{len(joint_names)} joints: {joint_names}")
    mapping = resolve_canonical_joints(joint_names, parent_indices)
    print("resolved canonical -> real joint name:")
    for canonical, idx in sorted(mapping.items()):
        print(f"  {canonical:16s} -> [{idx}] {joint_names[idx]}")
    return {"joint_names": joint_names, "resolved": {k: joint_names[v] for k, v in mapping.items()}}


@app.function(image=gltf_image, gpu=GPU_TIER, volumes={WEIGHTS_DIR: weights, RESULTS_DIR: results},
              secrets=R2_SECRET, timeout=600)
def export_clip_gltf(clip_id: str, job_id: str | None = None):
    """Stage 6c: the real fix (W8) -- export the ACTUAL reconstructed motion
    from a run_clip() result, not a neutral pose. One GLB per confidently-
    tracked dancer (each PersonResult carries its own animation ref per the
    motion-result.schema.json contract change, W8).

    Reads the npz run_clip() saved (per_frame[i][track_id]["skel_state"], now
    populated because sam_3d_body_estimator.py exposes the estimator's raw
    (J, 8) skel_state -- see mhr_head.py's _mhr_forward_core). Builds one
    (n_samples, J, 8) array per dancer and exports it.

    Body shape: the estimator also predicts a 45-dim MHR shape vector per person
    per frame, which this export used to discard, so every dancer rendered with
    the mean MHR body. Each track's shape is now averaged across its observed
    frames (per-dim median) and baked into that track's rest mesh before export
    -- see _character_with_shape for why baking, not a pymomentum blend-shape
    call, is the route. Measured effect on solo-01 is real but modest (2.5 mm
    mean / 2.1 cm max surface displacement): MHR's shape basis moves the SURFACE
    only. Limb lengths and overall size come from the scale parameters, which
    already reach the GLB inside the per-frame skel_state and are NOT re-derived
    here (see the report in docs/GATE-REPORT.md for the numbers, including the
    ~9% frame-to-frame bone-length wobble that averaging shape does not fix).

    Gap-filling for samples where a dancer wasn't reconstructed (occluded,
    out of frame, or not yet confidently tracked): holds the nearest earlier
    observed skel_state (or the first observed one, for a leading gap).
    ponytail: this is a naive hold, not Kalman/interpolation -- it exists only
    so save_gltf_from_skel_states gets a frame for every sample_times_s slot
    (a hard contract requirement), not to make gaps look good. Milestone A's
    real interpolation/suppression chain (out of W8 scope, see
    docs/GATE-REPORT.md) replaces this; a held pose plays as a visible freeze,
    which is honest -- it does not claim motion that wasn't observed.

    W10: after pymomentum writes the GLB, region_mask.split_glb_by_region
    rewrites it in place, splitting the one MHR mesh into named `region_<id>`
    sub-meshes (docs/OPEN-DECISIONS.md E3) -- see that module's docstring for
    why this is a one-time structural GLB edit, not a per-frame one, and why
    it resolves REGIONS' canonical joint names against the real skeleton via
    a tolerant matcher instead of a hardcoded naming guess.
    """
    import os
    import sys

    import numpy as np
    import pymomentum.geometry as pym_geo

    sys.path.insert(0, "/app/motion-api-tools")
    from region_mask import RegionMappingError, split_glb_by_region

    npz_path = f"{RESULTS_DIR}/{clip_id}.npz"
    # The same read-after-write window run_clip already guards `uploads`
    # against, on the other side of the same handoff: run_clip writes the npz
    # and commits, then calls this function, whose container may have a mount
    # snapshot older than that commit. Hit live on 2026-09-21 -- a real
    # reconstruction of solo-07 finished, wrote the npz (verified present on
    # the Volume afterwards), and this line raised
    # "[Errno 2] No such file or directory: /results/<clip>.npz", surfacing as
    # a retryable `export_error` on a job that had already done all the GPU
    # work. A Volume is storage, not a queue: there is no delivery guarantee
    # beyond eventual consistency, so the reload has to be explicit.
    if not os.path.exists(npz_path):
        print(f"{npz_path} not visible yet -- reloading the results Volume")
        results.reload()
    print(f"loading {npz_path}")
    data = np.load(npz_path, allow_pickle=True)
    if bool(data["refused"]):
        raise RuntimeError(f"{clip_id} was refused by run_clip ({data['refusal_reason']}), nothing to export")

    per_frame = data["per_frame"]  # array of dicts, one per sample
    confident_track_ids = data["confident_track_ids"].tolist()
    n_samples = len(per_frame)

    lod_path = f"{WEIGHTS_DIR}/mhr-assets/lod3.fbx"
    mhr_path = f"{WEIGHTS_DIR}/facebook__sam-3d-body-dinov3/assets/mhr_model.pt"

    # The real sample rate, derived from the npz's own timeline rather than
    # hardcoded. run_clip takes an `fps` argument, so the old hardcoded 15.0
    # silently mislabelled the timing of any run that did not use the default
    # -- a 30 fps reconstruction was exported as a 15 fps animation, i.e.
    # playing at half speed. sample_times_s is written by process_clip as
    # `i / fps`, so the spacing IS the sample rate, and deriving it here also
    # keeps a standalone re-export correct without threading a parameter
    # through that could disagree with the data it describes.
    sample_times_s = data["sample_times_s"]
    if len(sample_times_s) < 2:
        raise ValueError(f"{clip_id}: need at least 2 samples to establish a frame rate")
    fps = round(1.0 / float(sample_times_s[1] - sample_times_s[0]), 6)
    print(f"sample rate from npz timeline: {fps} fps ({len(sample_times_s)} samples)")

    # Body shape, loaded once for the whole clip: the estimator predicts a 45-dim
    # MHR shape vector per person per frame and the export used to drop it on the
    # floor, so every dancer rendered as the mean MHR body.
    neutral_verts, shape_vectors = _mhr_shape_basis(mhr_path)
    base_character = pym_geo.Character.load_fbx(lod_path)
    lod_rest = np.asarray(base_character.mesh.vertices, dtype=np.float64)
    lod_to_mhr, nn_dist = _nearest_vertex_map(lod_rest, neutral_verts)
    print(f"lod3 ({len(lod_rest)} verts) -> MHR basis ({len(neutral_verts)} verts): "
          f"nn dist mean={nn_dist.mean():.4f} max={nn_dist.max():.4f} cm")
    if nn_dist.mean() > 1.0:
        # The two assets must be the same body in the same rest pose and units
        # (measured: 0.297 cm mean, 1.79 cm max). A large number here means a
        # different LOD/model asset or a unit change -- transferring the shape
        # displacement anyway would silently warp the mesh, which is the exact
        # failure mode this pipeline must not ship.
        raise ValueError(
            f"LOD mesh does not match the MHR shape basis (nn dist mean {nn_dist.mean():.3f} cm). "
            "Refusing to bake body shape from a mismatched asset."
        )

    out_paths = {}
    shape_vectors_out = {}
    for track_id in confident_track_ids:
        skel_states = np.zeros((n_samples, 127, 8), dtype=np.float32)

        # Pass 1: collect the observed poses by sample index.
        observed: dict[int, "np.ndarray"] = {}
        shape_samples = []
        for i in range(n_samples):
            person = per_frame[i].get(track_id) if isinstance(per_frame[i], dict) else None
            if person is not None and "skel_state" in person:
                observed[i] = np.asarray(person["skel_state"], dtype=np.float32)
                if "shape_params" in person:
                    shape_samples.append(np.asarray(person["shape_params"], dtype=np.float64).ravel())
        n_observed = len(observed)
        if not observed:
            print(f"track {track_id}: no observed samples, skipping export")
            continue

        # Pass 2: forward-hold, and BACK-FILL the leading gap from the first
        # observed pose.
        #
        # The leading gap used to be filled with np.zeros((127, 8)). That is
        # NOT a neutral pose: a skel_state row carries a quaternion, and an
        # all-zero quaternion has zero norm, so normalizing it yields NaN.
        # A single NaN frame propagates through the skeleton's world matrices
        # and makes the ENTIRE model vanish in any glTF viewer -- verified
        # against solo-01, whose frame 0 is one of its 5 unreconstructed
        # frames: 128 of 235 animation channels had a NaN at frame 0 and
        # nothing rendered at all.
        #
        # Back-filling is the same honesty argument the forward-hold already
        # makes (a held pose plays as a visible freeze, it does not claim
        # motion that was not observed), just applied at the start of the
        # clip instead of the middle. It also needs no knowledge of the
        # skel_state layout, unlike constructing a true identity pose.
        first_observed_idx = min(observed)
        held = observed[first_observed_idx]
        for i in range(n_samples):
            if i in observed:
                held = observed[i]
            skel_states[i] = held

        if not np.all(np.isfinite(skel_states)):
            # Never export a NaN/Inf animation: it fails silently at render
            # time (an invisible model), which is the worst possible failure
            # mode -- it looks like a viewer bug, not a pipeline bug.
            bad = np.argwhere(~np.isfinite(skel_states))
            raise ValueError(
                f"track {track_id}: non-finite skel_state values before export "
                f"({len(bad)} entries, first at sample {bad[0][0]} joint {bad[0][1]}). "
                "Refusing to write a GLB that would render as nothing."
            )

        print(f"track {track_id}: {n_observed}/{n_samples} samples observed "
              f"(first at {first_observed_idx}, leading gap back-filled)")

        # One body shape for the whole track: a body does not change between
        # frames, so the per-frame estimates are repeat measurements of one
        # value. PER-DIM MEDIAN, not the mean: on solo-01's 291 observed frames
        # the two agree to ||mean - median|| = 0.121 against ||mean|| = 2.883
        # (4.2%, and a 10%-trimmed mean is 0.062 from the mean), so on a clean
        # clip the choice is nearly free -- but the per-frame spread is large
        # (per-dim std 0.199 mean / 0.459 max; per-frame L2 distance from the
        # mean averages 1.42 and reaches 2.99, i.e. half the vector's own norm),
        # and a partial-view or occluded frame is exactly the kind of sample
        # that lands far out. The median bounds any single bad frame's influence
        # at zero extra cost; the mean does not.
        character = base_character
        if shape_samples:
            shape_vec = np.median(np.stack(shape_samples), axis=0)
            character, rest_delta = _character_with_shape(
                base_character, shape_vec, shape_vectors, lod_to_mhr
            )
            mag = np.linalg.norm(rest_delta, axis=1)
            shape_vectors_out[str(track_id)] = shape_vec.tolist()
            print(f"track {track_id}: shape from {len(shape_samples)} frames, "
                  f"||shape||={np.linalg.norm(shape_vec):.3f}, per-frame std mean="
                  f"{np.stack(shape_samples).std(0).mean():.3f}; rest-mesh displacement "
                  f"mean={mag.mean():.4f} cm max={mag.max():.4f} cm")
        else:
            # Honesty (DESIGN.md §7h): no estimate at all means the mean MHR body
            # is rendered, and api.py must label it default_assumed rather than
            # present it as this dancer's measured proportions.
            print(f"track {track_id}: no shape_params in the npz, exporting the mean MHR body")

        out_path = f"{RESULTS_DIR}/{clip_id}_track{track_id}.glb"
        pym_geo.Character.save_gltf_from_skel_states(out_path, character, fps, skel_states)
        print(f"SAVED {out_path} (single mesh, pre-region-split)")

        # In place: same path, same animation/skin, mesh now split into named
        # region_<id> sub-meshes. Fails loudly rather than shipping a GLB with
        # no masking surface -- DESIGN.md §7h's honesty standard applies to
        # this mapping just as much as to what gets rendered from it.
        try:
            region_triangle_counts = split_glb_by_region(out_path, out_path)
        except RegionMappingError as e:
            raise RuntimeError(
                f"{clip_id} track {track_id}: real MHR skeleton's joint names didn't match "
                f"REGIONS closely enough to mask body parts safely: {e}"
            ) from e
        empty_regions = [r for r, n in region_triangle_counts.items() if n == 0]
        if empty_regions:
            print(f"track {track_id}: regions with NO surface (check before trusting masking): {empty_regions}")
        print(f"track {track_id}: region triangle counts: {region_triangle_counts}")

        print(f"SAVED {out_path} (region-split)")

        # INTEGRATION (second pass): the interpolation rewrite runs LAST, after
        # the region split, and the order is load-bearing in one direction only.
        # Both stages rewrite the same GLB with pygltflib. split_glb_by_region
        # leaves animation channels and samplers untouched but DOES rebuild the
        # binary chunk (it appends new accessors for the per-region sub-meshes),
        # so running the rewrite first would still leave LINEAR in the file --
        # but unverified, because nothing would re-read the shipped bytes.
        # Running it last means `_rewrite_interpolation_linear`'s three checks
        # (binary chunk untouched by the rewrite, every sampler LINEAR, no
        # non-finite float in the chunk) all execute against the file that is
        # actually shipped, and the finite check now covers the split's new
        # vertex accessors as well as the animation.
        #
        # pymomentum always writes STEP; nothing downstream can ask it not to.
        # See _rewrite_interpolation_linear for the measurements behind LINEAR.
        interp = _rewrite_interpolation_linear(out_path)
        out_paths[track_id] = out_path
        print(f"SAVED {out_path} (region-split, {interp['n_rewritten']}/{interp['n_samplers']} "
              f"samplers rewritten to {interp['interpolation']})")

    # W4: api.py builds MotionResult from the npz + this manifest without
    # needing pymomentum/CUDA installed -- it never needs to know the GLB
    # naming scheme or fps used here, only this file's contents.
    import json
    manifest = {
        "clip_id": clip_id,
        "fps": fps,
        # How a PLAYER fills the time between two keyframes. Deliberately NOT
        # the same thing as MotionResult's per-sample `provenance.interpolated`,
        # which marks a whole pose this pipeline did not observe and held or
        # filled in. A LINEAR sampler does not make any sample "interpolated"
        # in the contract's sense -- every keyframe is still exactly what was
        # reconstructed. Recorded here so the two can never be conflated.
        "gltf_interpolation": GLTF_INTERPOLATION,
        "glb_paths": {str(tid): os.path.basename(p) for tid, p in out_paths.items()},
        # The exact vector baked into each GLB, so MotionResult.persons[].shape_params
        # reports what was rendered instead of re-deriving (and disagreeing with) it.
        # No schema change: ShapeParams already means "one vector for the whole clip,
        # estimated from well-observed frames" -- this is the first time that is true.
        "shape_params": shape_vectors_out,
    }
    with open(f"{RESULTS_DIR}/{clip_id}.export-manifest.json", "w") as f:
        json.dump(manifest, f)

    # Materialise the MotionResult here, once, instead of api.py rebuilding it
    # from the npz on every GET. That was the last thing keeping the npz alive:
    # api.py's _build_motion_result read it on every single request, so "the
    # npz is never read after export" was not actually true. Now it is, and
    # sweep_expired can reap the npz (it only does so once this file exists --
    # never delete the source before the replacement is on disk).
    #
    # Gzipped because it is JSON: 7.15 MB -> 1.49 MB measured on solo-01, and
    # api.py serves it straight back out without re-reading 296 x 127 joints
    # through a Python quaternion multiply on every request.
    import gzip
    import sys
    sys.path.insert(0, "/app")
    import motion_result

    perf_path = f"{RESULTS_DIR}/{clip_id}.performance.json"
    perf = json.load(open(perf_path)) if os.path.exists(perf_path) else None
    beats_path = f"{RESULTS_DIR}/{clip_id}.beats.json"
    beats = json.load(open(beats_path)) if os.path.exists(beats_path) else None
    try:
        doc = motion_result.build_motion_result(
            job_id or f"job_{clip_id}", clip_id,
            open(npz_path, "rb").read(), manifest, perf, beats,
        )
        with open(f"{RESULTS_DIR}/{clip_id}.motion-result.json.gz", "wb") as f:
            f.write(gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), 6))
        materialised = True
    except Exception as e:  # noqa: BLE001
        # Not fatal: the npz is still there and api.py falls back to building
        # from it, exactly as it did before. Loud, though -- a lesson stuck on
        # the fallback path is one the sweeper will never reclaim space for.
        print(f"WARNING: could not materialise MotionResult for {clip_id}: {e}")
        materialised = False

    results.commit()

    # Publish the delivered bytes to R2 (infrastructure.md decision 3, migration
    # step 5). Here, not in api.py, because this is the first instant at which
    # every one of them exists -- and doing it once at job completion instead of
    # on each request is the difference between an immutable edge-cacheable
    # object and a Python byte proxy.
    #
    # The source video is NOT published here: api.py already holds those bytes
    # at upload time and publishes them there, which saves reading a 5 MB object
    # back out of a Volume it never needed to be read from.
    #
    # Best-effort on purpose. An R2 outage must not fail a job that produced a
    # perfectly good reconstruction: api.py falls back to the Volume proxy for
    # any object R2 does not have (no range requests on that path, but a working
    # lesson beats a failed one). Loud, though -- a lesson stuck on the fallback
    # is one whose video cannot be scrubbed.
    published = _publish_to_r2(clip_id, list(out_paths.values()), materialised)

    return {"clip_id": clip_id, "glb_paths": out_paths, "n_dancers": len(confident_track_ids),
            "motion_result_materialised": materialised, "r2_published": published}


def _publish_to_r2(clip_id: str, glb_paths: list[str], materialised: bool) -> list[str]:
    """Upload this lesson's GLBs and MotionResult to R2. Returns the keys written."""
    import sys
    sys.path.insert(0, "/app")
    import storage

    if not storage.enabled():
        print(f"[r2] not configured (missing {', '.join(storage.missing_env())}) -- "
              f"{clip_id} will be served from the Volume, without range requests")
        return []

    written = []
    try:
        for path in glb_paths:
            written.append(storage.put_file(
                storage.glb_key(os.path.basename(path)), path, "model/gltf-binary"))
        if materialised:
            written.append(storage.put_file(
                storage.motion_result_key(clip_id),
                f"{RESULTS_DIR}/{clip_id}.motion-result.json.gz",
                "application/json",
                # Stored gzipped; declaring the encoding is what lets a browser
                # (and api.py's passthrough) decompress it transparently instead
                # of handing the caller a bag of bytes.
                content_encoding="gzip",
            ))
        print(f"[r2] published {len(written)} objects for {clip_id}")
    except Exception as e:  # noqa: BLE001 -- never fail a good job on a storage blip
        print(f"WARNING: R2 publish incomplete for {clip_id} ({len(written)} written): {e}")
    return written


# The Volumes are declared here even though this function never reads a
# mounted path: Volume.listdir/remove_file are @live_method, so the objects
# have to be HYDRATED, and listing them in `volumes=` is what guarantees Modal
# resolves them for this container. All access below goes through the client
# API, not the mount.
@app.function(image=sweeper_image, schedule=modal.Period(days=1), timeout=1800,
              volumes={RESULTS_DIR: results, UPLOADS_DIR: uploads}, secrets=R2_SECRET + OBS_SECRETS)
def sweep_expired(dry_run: bool = False):
    """Runs `_sweep_expired` and reports it to Sentry if it dies.

    A sweeper that crashes every night is a retention promise with nothing
    behind it, and nobody reads a one-day log for a job that "just runs".
    """
    import sys
    sys.path.insert(0, "/app")
    import observability
    try:
        return _sweep_expired(dry_run)
    except Exception as e:  # noqa: BLE001 -- reported, then re-raised so Modal marks the run failed
        observability.capture(e, "sweep_expired", dry_run=dry_run)
        raise


def _sweep_expired(dry_run: bool):
    """Retention, on a clock. Two jobs, both of which only ever delete.

    **1. Reap superseded npz files.** A clip whose `.motion-result.json.gz`
    exists has nothing left that reads its npz, so the npz goes. Deliberately
    here and not inside export_clip_gltf: deleting the source in the same
    breath as writing its replacement means a bad write takes both. Leaving it
    for the next sweep costs at most 24 hours of a 3.40 MB file and keeps the
    npz available as api.py's fallback until something has actually read the
    replacement.

    **2. Expire lessons nobody opens.** `retention.TTL_DAYS` since last access,
    where "access" is a lesson being opened (api.py touches `.last-access.json`
    when it serves a result). A lesson with no touch file has never been opened
    since this shipped; its export-manifest mtime stands in as the clock start,
    so old lessons are not all deleted on the first run.

    `dry_run` defaults to False because the SCHEDULE calls this with no
    arguments, and a scheduled sweeper that quietly does nothing is exactly the
    failure this whole change exists to fix -- a retention promise with no
    retention behind it. To inspect before trusting it:

        modal run modal_app.py::sweep_expired --dry-run
    """
    import sys
    import time
    sys.path.insert(0, "/app")
    import retention

    listing = {e.path.lstrip("/"): e for e in results.listdir("/")}
    now = time.time()

    def suffixed(suffix):
        return {n[: -len(suffix)] for n in listing if n.endswith(suffix)}

    removed = suffixed(".removed.json")          # already taken down; nothing left to do
    materialised = suffixed(".motion-result.json.gz")
    have_npz = suffixed(".npz")
    live = (materialised | have_npz) - removed

    def last_opened(clip_id):
        touch = retention.read_json(results, retention.touch_path(clip_id))
        if touch and "at" in touch:
            return touch["at"]
        # Never opened since touch tracking shipped. Fall back to when the
        # lesson was built, so pre-existing lessons age from their real date
        # rather than all surviving (or all dying) on the first sweep.
        entry = (listing.get(f"{clip_id}.export-manifest.json")
                 or listing.get(f"{clip_id}.npz"))
        return entry.mtime if entry else now

    expired = {c: round((now - last_opened(c)) / 86400, 1)
               for c in sorted(live) if retention.is_expired(last_opened(c), now)}
    # An npz is superseded once its replacement exists; skip the ones whose
    # whole lesson is about to go anyway.
    reap_npz = sorted((have_npz & materialised) - removed - set(expired))

    print(f"sweep: {len(reap_npz)} superseded npz, {len(expired)} lessons past "
          f"{retention.TTL_DAYS}d since last open, {len(live) - len(expired)} kept "
          f"(dry_run={dry_run})")
    for clip_id, age in expired.items():
        print(f"  expired {clip_id}  ({age}d since last open)")

    if dry_run:
        return {"dry_run": True, "would_reap_npz": reap_npz,
                "would_expire": sorted(expired), "kept": len(live) - len(expired)}

    for clip_id in reap_npz:
        try:
            results.remove_file(f"/{clip_id}.npz")
        except FileNotFoundError:
            pass
    for clip_id in expired:
        # The same deletion path a takedown uses, on purpose: if these two ever
        # disagree about what a lesson is made of, the weaker one is a leak.
        retention.delete_clip(uploads, results, clip_id, f"job_{clip_id}", "expired")
    # No commit(): every delete above went through the client API and is
    # already durable. See retention.delete_clip.
    return {"dry_run": False, "reaped_npz": reap_npz,
            "expired": sorted(expired), "kept": len(live) - len(expired)}


# ---------------------------------------------------------------------------
# The HTTP service (infrastructure.md decision 1, migration step 1).
#
# api.py deliberately has no torch/CUDA/pymomentum dependency, so it could run
# anywhere. It runs *here* because it is already a Modal client: it constructs
# `modal.Volume.from_name(...)` at import and dispatches through
# `modal.Function.from_name(APP_NAME, "run_clip").spawn()`. Hosting it anywhere
# else means a second platform, a second deploy pipeline, and a Modal API token
# sitting in someone else's secret store. Hosting it here means one account and
# one `modal deploy`.
#
# The coupling is exactly one decorator deep, which is the only reason choosing
# the tightly-coupled option is defensible: `uvicorn api:app` still runs this
# unchanged on Railway, Fly or a box, and that escape hatch is what makes this
# reversible in a day rather than a quarter.
#
# `ignore=` keeps the 1.9 GB vendored Fast-SAM-3D-Body tree out of a CPU image
# that will never import it -- api.py's whole point is that it does not.
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOTION_API_DIR = os.path.dirname(os.path.abspath(__file__))

api_image = (
    modal.Image.debian_slim(python_version="3.12")
    # The ffmpeg/ffprobe BINARIES, for the upload fingerprint that skips a GPU
    # reconstruction when the same dance has already been processed. Invoked as
    # a subprocess, never linked, so no licence reaches this repo. Without them
    # dedupe silently degrades to exact-sha256 -- and /health says so -- but
    # $0.08 per avoidable reconstruction is worth an apt package.
    .apt_install("ffmpeg")
    # One dependency list, not two: requirements-api.txt is what a laptop
    # installs and what this image installs, so they cannot drift.
    .pip_install_from_requirements(os.path.join(MOTION_API_DIR, "requirements-api.txt"))
    # Mounted so that api.py's own `Path(__file__).parent.parent.parent /
    # "packages" / "motion-contract" / "python"` resolves inside the container
    # exactly as it does on a laptop. Reproducing the repo's shape is cheaper
    # and less surprising than patching the path at import.
    # migrations/ is 11 KB and deliberately NOT excluded: `modal shell` into
    # this container is the one place that is guaranteed to be able to reach a
    # private Neon endpoint, so `python3 migrate.py` has to work from here.
    .add_local_dir(MOTION_API_DIR, remote_path="/app/services/motion-api",
                   ignore=["vendor/**", "**/__pycache__/**", "*.pyc"])
    # The one file the `vendor/**` exclusion above must NOT take with it, put
    # back at the exact path the repo has it at.
    #
    # THIRD INTEGRATION PASS, broken only in combination. `deployment` wrote
    # that exclusion when api.py had no vendored dependency at all -- its whole
    # point is that it never imports torch or the CV tree, and 1.9 GB of
    # Fast-SAM-3D-Body has no business in a CPU image. `grounding-wiring`, cut
    # from a base with no api_image in it, then gave `motion_result` a
    # module-level `import world_placement_probe`, and that module does a
    # module-level `import skeleton_constraints` off `vendor/`. api.py imports
    # motion_result at module level, so the composed result is that
    # `modal deploy` SUCCEEDS and then every single request to the ASGI app
    # dies in `web()` with ModuleNotFoundError. Git had no conflict to raise
    # (two different files), and no test caught it (every suite runs from a
    # checkout where vendor/ is simply there on disk).
    #
    # 17 KB of pure numpy, no torch. Mounted at its repo path rather than flat
    # so that world_placement_probe's own `sys.path.insert(_HERE / "vendor/...")`
    # finds it with no import-path change in any module -- gltf_image mounts
    # the same file flat at /app because that image has a flat /app.
    .add_local_file(os.path.join(MOTION_API_DIR, "vendor", "fast-sam-3d-body",
                                 "tools", "skeleton_constraints.py"),
                    "/app/services/motion-api/vendor/fast-sam-3d-body/tools/skeleton_constraints.py")
    .add_local_dir(os.path.join(REPO_ROOT, "packages", "motion-contract", "python"),
                   remote_path="/app/packages/motion-contract/python",
                   ignore=["**/__pycache__/**", "*.pyc", ".venv/**"])
    .add_local_dir(os.path.join(REPO_ROOT, "packages", "motion-contract", "schema"),
                   remote_path="/app/packages/motion-contract/schema")
)


@app.function(
    image=api_image,
    secrets=R2_SECRET + DB_SECRET + ORIGIN_SECRET + OBS_SECRETS,
    # Scale to zero. A cold start is a few seconds on the upload endpoint,
    # where it is invisible, and on the first two-second job poll, where it is
    # also invisible. min_containers=1 pins ~$45/month of always-on container
    # and should not be paid speculatively -- only if a real user complains
    # (infrastructure.md §2, "honest costs of this choice").
    min_containers=0,
    # One upload can be 200 MB and one job poll is a single Volume read, so the
    # ceiling here is memory, not CPU. 100 is Modal's documented practical
    # maximum per container and leaves the workspace's 200 req/s limit as the
    # real bound.
    timeout=600,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    import sys
    sys.path.insert(0, "/app/services/motion-api")
    # Before the api import, not after: the FastAPI/Starlette integrations
    # patch the class at init, so an app built first is never instrumented.
    import observability
    observability.init("web")
    from api import app as fastapi_app
    return fastapi_app


@app.function(image=sweeper_image, secrets=R2_SECRET, timeout=300)
def verify_r2_access():
    """Does the `stepwise-r2` Modal Secret actually work against the bucket?

    The Secret was created 2026-03 and nothing had used it since, so "the keys
    are probably right" was an assumption worth one container-second to delete.
    This does the same round trip as verify_r2.py -- write, range-read, check
    the bytes, delete -- from inside Modal, with the Secret as the only source
    of credentials. It never prints a credential, only which names are present.

        modal run modal_app.py::verify_r2_access
    """
    import sys
    import urllib.request
    sys.path.insert(0, "/app")
    import storage

    if not storage.enabled():
        return {"ok": False, "missing": storage.missing_env()}

    key = "diagnostic/modal-range-probe.bin"
    data = bytes(range(256)) * 64
    storage.put_bytes(key, data, "application/octet-stream")
    try:
        req = urllib.request.Request(storage.url_for(key), headers={"Range": "bytes=100-199"})
        with urllib.request.urlopen(req) as r:
            body, status = r.read(), r.status
            content_range = r.headers.get("Content-Range")
    finally:
        storage.delete(key)
    out = {"ok": status == 206 and body == data[100:200], "status": status,
           "content_range": content_range, "bucket_env_set": True}
    print(f"[verify_r2_access] {out}")
    return out


@app.local_entrypoint()
def main():
    """Run the stages in order, stopping at the first failure."""
    print("\n=== stage 1: GPU ===")
    print(verify_gpu.remote())
    print("\n=== stage 2: gated weights ===")
    print(download_weights.remote())
    print("\n=== stage 3: inspect ===")
    inspect_weights.remote()
