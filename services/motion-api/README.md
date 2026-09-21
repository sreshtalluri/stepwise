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
