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


@app.local_entrypoint()
def main():
    """Run the stages in order, stopping at the first failure."""
    print("\n=== stage 1: GPU ===")
    print(verify_gpu.remote())
    print("\n=== stage 2: gated weights ===")
    print(download_weights.remote())
    print("\n=== stage 3: inspect ===")
    inspect_weights.remote()
