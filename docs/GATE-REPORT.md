# Feasibility gate report (W1)

Branch: `worktree-modal-gate`. Covers `docs/PRD.md` §2's G1–G7. Written after
running the real pipeline on real Modal GPU hardware against a real clip —
every number below is measured, not estimated, unless marked otherwise.

## Gate decision

**Not a clean yes or no — and it shouldn't be forced into one.** Every piece
of the pipeline that could plausibly have killed the project (gated weights,
license conflict, the two-incompatible-environments trap, the detector
adapter's real bugs, CUDA actually activating, the reconstruction itself)
is now verified, on real hardware, with real numbers. Nothing found in ~this
pass blocks continuing. But the literal deliverable the PRD asks for — one
clip's *reconstructed* body, animated, on a phone, next to the original video
— has not been produced yet. What exists instead is two separate, both-real
proofs that don't yet touch each other: the reconstruction pipeline produces
correct per-frame data (§ Measured results), and the export mechanism
produces a valid GLB (§ G6), but the GLB was driven by a neutral pose, not by
the reconstructed data. One additive, precisely-scoped code change closes
that gap (§ What's left). Recommendation: **continue** — spend the
remaining time closing that one gap and doing the actual phone check, rather
than stopping now on ambiguity that a few more hours resolves either way.

## What's verified, with real numbers

**G1 — weights.** Done before this pass. `facebook/sam-3d-body-dinov3`
downloaded, 2.81 GB, GPU verified (L40S, CUDA 12.4, 47.2 GB free).

**Bundled MHR checkpoint vs. the separate assets.zip.** The PRD assumed
`mhr_model.pt` (bundled with the SAM 3D Body checkpoint) was parameters only,
and that LOD meshes required a separate ~190 MB release download. Verified
by loading it directly (`torch.jit.load`) and inspecting its buffers: it is a
**complete skinned character** — 18,439 verts, 36,874 faces, a 127-joint
skeleton, skinning weights, blendshapes, and pose correctives. Downloaded the
real `assets.zip` (v1.0.1, 198.9 MB) independently and confirmed it contains
7 LOD `.fbx` files (0–6) plus the same `mhr_model.pt`, `compact_v6_1.model`,
and per-LOD corrective blendshapes. **Its in-zip `LICENSE.txt` is plain
Apache-2.0**, no extra restriction — this resolves the "unverified" line in
the `licensing-compliance` branch's `docs/LICENSES.md`; that branch should be
updated to reflect it. assets.zip turned out to still be necessary, but for a
different reason than assumed: pymomentum's `Character` object is loaded
from an FBX (see G6), not constructed from the bundled model's raw buffers.

**G2 — licensing.** Not this branch's task (see `licensing-compliance`,
commit `d1683ed`, unmerged). The one open item it flagged — the MHR asset
license — is now closed (above).

**G3 — the real CV image.** Built and green on real Modal GPU hardware:
Python 3.11, torch 2.5.1+cu124, Detectron2 (compiled from source against
that exact CUDA toolkit), RTMO via `rtmlib` on **ONNXRuntime with
CUDAExecutionProvider actually active** (verified, not assumed — see below),
ByteTrack. `ultralytics`, `tensorrt-cu12*`, and `smplx`/`chumpy` removed per
G2/G3. Getting here took seven real, separate bugs, each verified and fixed
one at a time rather than guessed at in bulk (full detail in commit
messages, `6357fcb` onward):

1. `bytetracker`'s published PyPI release pins `lap==0.4.0`, which doesn't
   build on Python 3.11 or against this image's numpy. Fixed by installing
   `bytetracker` from GitHub `main`, which already switched to `lapx`.
2. numpy/setuptools autodetect a `clang` compiler on an image that only has
   `gcc`/`g++`. Fixed with explicit `CC=gcc CXX=g++` on the Detectron2 build.
3. `--no-build-isolation` installs need `wheel` present in the outer
   environment (isolation normally provides it automatically).
4. `onnxruntime-gpu` dlopens cuDNN/cuBLAS at session-creation time rather
   than declaring them as pip dependencies; torch's own install already pulls
   in `nvidia-cudnn-cu12` etc., but nothing put them on the linker path.
   Fixed by registering every `nvidia-*-cu12` package's `lib/` dir with
   `ldconfig`.
5. ONNXRuntime ≥1.21 needs an explicit `onnxruntime.preload_dlls()` call
   before the first `InferenceSession`; it doesn't rely on
   `ldconfig`/`LD_LIBRARY_PATH` the way most CUDA libraries do.
6. `rtmlib`'s own `requires_dist` lists plain `onnxruntime` (CPU), which pip
   installs *alongside* `onnxruntime-gpu` into the same `onnxruntime/`
   site-packages directory, silently corrupting it — `CUDAExecutionProvider`
   vanishes from `get_available_providers()` with zero error, only a
   pip warning easy to miss in a long build log. Fixed with `--no-deps`.
7. **The actual root cause**, visible only once #6 stopped masking it:
   unpinned `onnxruntime-gpu` resolved to 1.30.0, which requires cuDNN 9 +
   **CUDA 13** and fails at session-creation with an explicit
   `Require cuDNN 9.* and CUDA 13.*` error — this image is pinned to CUDA
   12.4 because Detectron2 compiles against exactly that toolkit (G3).
   Fixed by pinning `onnxruntime-gpu==1.20.2`, the last CUDA-12-era release.

Each of these is a genuine environment bug, not a typo — several would have
silently produced a CPU-only pipeline (10-50x slower, and *wrong* about its
own cost/throughput) with no error at all. This is the concrete shape of
"the two-environment split is the #1 install trap" the PRD warned about,
one layer down from what the PRD anticipated.

**G4 — eager inference, correctness first.** No TensorRT anywhere. Confirmed
directly: `onnxruntime.get_available_providers()` includes
`CUDAExecutionProvider`, and the RTMO session's own
`session.get_providers()` reports `CUDAExecutionProvider` first, on the
actual detector instance used downstream — not just at the module level.

**G5 — the detector adapter.** Read `rtmlib`'s actual source
(`rtmo.py`/`post_processings.py`) rather than trusting the brief's
description of the bug, and confirmed both defects independently:
- `RTMO.postprocess` computes boxes/scores via `multiclass_nms`, but the
  `keep` indices it returns are relative to the **score-thresholded
  subset**, while upstream applies them to the **unfiltered**
  keypoints/scores array — silently misaligning boxes and keypoints whenever
  `score_thr` drops anything. `tools/rtmo_detector.py`'s
  `postprocess_aligned` redoes the filter → NMS pipeline so every array
  stays paired, verified by a regression test
  (`test_boxes_and_keypoints_stay_aligned_after_score_filter`) that
  specifically reproduces the misalignment with two people, one of whom
  gets filtered.
- Zero detections fabricate `np.zeros_like(keypoints[0])` upstream (a fake
  person standing at the origin) instead of returning nothing. Fixed, and
  verified on **real GPU hardware** against random noise: `run_human_detection`
  returned genuinely empty `(0,4)`/`(0,17,3)` arrays, not a fabricated pose.
- ByteTrack integrated (from `kadirnar/bytetrack-pip`, MIT), with IoU-based
  re-association back to per-frame keypoints since ByteTrack only tracks
  boxes. 7 unit tests, CPU-only, no GPU/ONNX session needed, all passing.

**Scope note, mid-gate.** The user revised the MVP scope while this work was
in progress (commit `313f959`, 2026-09-18): multiple dancers are now in
scope, not just one — RTMO/ByteTrack are multi-person by design already, and
capping at one would have meant discarding tracks the pipeline already
produces. `rtmo_detector.py` and `process_clip.py` were updated accordingly
(every detected dancer is reconstructed per frame, keyed by ByteTrack id;
cross-dancer identity-swap correction stays out of scope, per the revision).

## Measured results

Real clip, real detector (no oracle boxes), real Modal L40S:

| | |
|---|---|
| Clip | `evaluation/clips.yaml`'s `solo-01`, 19.7s, 576×1024, tagged `baseline` |
| Frames sampled | 296 (15 fps) |
| Frames reconstructed | 291 (98.3%) |
| Pipeline-internal time | 78.0s → **3.79 fps** |
| Wall clock (incl. model load/warmup) | 107.8s (~30s load overhead) |
| Peak VRAM | 3.69 GB (of 47.2 GB available) |
| Cost | **$0.058/clip** at L40S's $1.95/hr (warm compute only — excludes cold start, storage, retries, idle billing, per G7) |

3.79 fps lands close to the PRD's own "3.50 fps could not be re-verified"
figure — and this number *is* verified, with a real detector, which the
PRD's 5.28 fps figure (oracle boxes) explicitly is not. Multi-dancer cost
should be roughly linear (₽2x for two dancers per the scope-revision
estimate) — not measured directly this pass.

The gap between wall clock and pipeline-internal time (~30s) is real:
`SAM3DBodyEstimator.__init__` runs CUDA graph warmup and multi-batch-size
`torch.compile` warmup before processing a single frame. That cost is
per-container-start, not per-clip, so it amortizes in a real service that
keeps a warm worker — but a cold-start-per-request design would pay it
every time.

**Not yet run:** `solo-02` (fast motion), `solo-07` (floor work),
`group-synced-01` (two dancers). All three are already fetched and ready in
the `stepwise-eval` Volume.

## G6 — glTF export: mechanism proven, not yet wired to real data

Confirmed empirically, not assumed from the PRD:
- `pymomentum-gpu==0.1.114.post0` requires Python 3.12/3.13 + torch 2.8.0 —
  the two-environment split (`OPEN-DECISIONS.md` E5) is real and necessary.
- `Character.save_gltf_from_skel_states` and `Character.load_fbx` are
  `Character`-class-scoped (pybind11 `def_static` bindings), not
  module-level functions — a web search suggested this was renamed to
  `save_gltf_with_skel_states` in Sep 2025
  (`facebookresearch/momentum#569`), but that PR hasn't shipped in this
  pinned release: **the PRD's original name is correct for what's actually
  installed.** Recorded because "measure, don't trust" cuts both ways —
  including not trusting a claimed fix without checking what's installed.
- Confirmed signature: `save_gltf_from_skel_states(path, character, fps,
  skel_states: np.ndarray[float32] of shape (frames, joints, 8), markers=None,
  options=None)`.
- Loaded a real `Character` from `assets.zip`'s `lod3.fbx`: **127 joints —
  exactly matching the bundled `mhr_model.pt`'s skeleton.** This confirms
  the assets.zip LODs and the bundled checkpoint share one skeleton
  topology, which is what makes mixing them (estimator-computed pose +
  LOD-selected mesh) valid at all.
- Built and ran a smoke test: the bundled MHR TorchScript model's own
  `forward()` on a neutral (all-zero) pose → `skel_state` of shape
  `(1, 127, 8)` → `Character.save_gltf_from_skel_states` → a real, valid
  589 KB GLB (magic bytes confirmed), saved to the `stepwise-results` Volume.
  Two real shape bugs found and fixed getting here (see commit `235573f`):
  `model_parameters` is 204-dim, not 249 (the model concatenates a 45-dim
  zero vector internally before a 249-dim parameter transform); and a
  malformed `(frames, 1, joints, 8)` array (batch dim not dropped before
  repeating across frames) made `save_gltf_from_skel_states` **hang rather
  than raise** — a silent-hang failure mode worth remembering elsewhere,
  distinct from the silent-wrong-answer failure mode G5's bugs were.

**What's left, precisely scoped:** the smoke test's `skel_state` came from a
neutral pose, not from real per-frame reconstruction. Getting from here to
"the reconstructed dancer, animated" needs exactly one additive change:
`sam_3d_body/models/heads/mhr_head.py`'s `_mhr_forward_core` already computes
the exact right tensor internally (`curr_skinned_verts, curr_skel_state =
self.mhr(...)`, line ~591 of the vendored copy) but only exposes *derived*,
already-transformed values in the estimator's public output —
`pred_joint_coords` is `curr_skel_state`'s translation chunk scaled by 0.01,
and `joint_global_rots` is its quaternion chunk already converted to
rotation matrices. Reconstructing `skel_state` by inverting those
(un-scaling, rotmat→quaternion) is possible but adds real risk — a sign or
unit error there would silently produce a warped mesh, not an error, which
is exactly the failure mode a gate is supposed to catch, not introduce. The
correct fix is to add one line returning `curr_skel_state` directly from the
existing computation, threaded through to `process_one_image`'s output. Not
done in this pass; scoped clearly so it isn't rediscovered from scratch.

## Honesty boundary check (`DESIGN.md` §7h)

Nothing built this pass makes a user-facing claim, so §7h doesn't bind
code written here directly — but it constrains how these results should be
described going forward: **3.79 fps and 98.3% frame reconstruction on a
clean baseline clip is real and should not be undersold**, but it is not yet
evidence about the harder cases (turns, occlusion, re-entry) the honesty
design exists for. Note: none of the four eval clips already fetched
(`solo-01`, `solo-02`, `solo-07`, `group-synced-01`) are tagged for the
specific `turn + wrist-occlusion + re-entry` combination the PRD's
week-one deliverable names (`evaluation/clips.yaml`'s `solo-03` is tagged
for exactly this but has no URL yet). Don't claim occlusion/re-entry
handling is proven until that clip exists and runs.

## What's left before this gate can close cleanly

1. Wire real per-frame `skel_state` through `process_clip.py` → export stage
   (one additive change to `mhr_head.py`, above).
2. Fetch/film the `solo-03`-shaped clip (turn, back-facing, ideally with a
   wrist occlusion and a re-entry) and run it — this is the PRD's actual
   named week-one deliverable, not `solo-01`.
3. Produce the real animated GLB, play it beside the original video **on an
   actual phone**, with raw detector overlays visible — the literal check
   this gate exists to make, not yet done.
4. G8 (book six cohort members) — unstarted, not a code task.

None of this is speculative — every piece above it has already been proven
to work in isolation. This is assembly and one more measurement, not open
research.
