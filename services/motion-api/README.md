# motion-api

GPU pipeline: video in, `MotionResult` out. See `docs/PRD.md` for the plan.

## Modal setup

Two account prerequisites, both one-time:

1. **HuggingFace token.** Create a **read** token at
   <https://huggingface.co/settings/tokens>, then:
   ```sh
   modal secret create huggingface HF_TOKEN=hf_xxxxx --force
   ```
   It must belong to the same account that was granted access to
   `facebook/sam-3d-body-dinov3`.

2. **Payment method on Modal.** Required for *any* GPU function, even with free
   credit. <https://modal.com/settings/billing>

## Stages

Run in order. Each is independently runnable so a failure is diagnosable.

```sh
# stage 2 — gated access + cache the weights. CPU only, costs cents.
# Works before billing is set up thanks to the STEPWISE_GPU override.
STEPWISE_GPU= modal run modal_app.py::download_weights

# stage 3 — what actually landed in the Volume
STEPWISE_GPU= modal run modal_app.py::inspect_weights

# stage 1 — CUDA works on the card we plan to rent. Needs billing.
modal run modal_app.py::verify_gpu
```

## Two gotchas worth knowing

**Modal validates the whole app at load time.** A missing Secret or an
unaffordable GPU tier blocks *every* function in the file, including ones that
never touch it. Hence the `HF_SECRET` try/except and the `STEPWISE_GPU`
override — without them you cannot run a CPU function until billing is live.

**The environment pins are not arbitrary.** Python 3.11 / Torch 2.5.1 / cu124
comes from Fast-SAM-3D-Body's setup script, because Detectron2 compiles against
that CUDA toolkit. `pymomentum` is deliberately absent: its wheels target
Python 3.12/3.13 with Torch 2.8, which cannot coexist here. glTF export gets a
separate image and the two exchange plain arrays.

## W4: the HTTP layer (`api.py`)

`modal_app.py` is the GPU worker; `api.py` is the plain FastAPI service that
turns an HTTP upload into a dispatched Modal job and serves its status/result.
It never imports torch/CUDA/pymomentum -- run it anywhere with a Modal token:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-api.txt
modal deploy modal_app.py          # api.py looks up run_clip via Function.from_name
.venv/bin/python -m uvicorn api:app --port 8811
```

Endpoints: `POST /clips` (multipart upload -> dispatches, returns `job_id`
immediately), `GET /jobs/{job_id}` (poll -- the real job-status.schema.json
document, unmodified), `GET /jobs/{job_id}/result` (once succeeded -- the
assembled, schema-validated `MotionResult`), `POST /jobs/{job_id}/retry`
(only for `retryable: true` failures), `GET /assets/{asset_id}` (resolves a
`source_video.asset_id` / `AnimationRef.glb_asset_id` to bytes).

## The floor solve (`grounding.py`)

Pure numpy, no GPU, no Modal. `api.py` calls it once per clip to fill
`MotionResult.grounding`. Two swappable seams — `detect_foot_contacts`
(which samples are contact evidence, as weights in [0,1]) and
`fit_floor_plane` (weighted RANSAC) — plus `solve_grounding`, which owns the
`grounded`-vs-`none` decision and its thresholds. A learned foot-contact model
drops in as `solve_grounding(..., contact_detector=...)`.

```sh
python3 -m pytest test_grounding.py -q        # 13 tests, no GPU
python3 grounding.py /path/to/clip.npz        # measure one real clip
```

It reports `none` far more often than you would expect, and
`docs/GATE-REPORT.md`'s grounding addendum explains exactly why with numbers —
read it before assuming the solve is broken.

See `api.py`'s module docstring for the object-storage decision (Modal
Volumes, not S3) and the known scope boundary in `_build_motion_result`
(per-joint visibility/suppression and true world-space root placement are
Milestone A/W9 work, not built here).
