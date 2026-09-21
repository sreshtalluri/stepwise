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

## W8 addendum (2026-09-18): real motion export, multi-dancer, contract fix

Branch `w8-worker` off `w8-base`. No Modal GPU session was run this pass (see
"what's not measured" below) — everything in this addendum is a code change,
read against the vendored source, plus a schema/contract change validated by
the existing (real, running) test suites. Nothing here is a fabricated number.

**1. Neutral-pose gap (G6): closed, not yet run on real hardware.**
`sam_3d_body/models/heads/mhr_head.py`'s `_mhr_forward_core` now returns
`curr_skel_state` as an additive 6th tuple element (it was already computed
there, per this report's own "what's left" note above) — threaded through
`_head_forward_core`, `mhr_forward` (new `return_skel_state` kwarg, both its
compiled and non-compiled/CUDA-graph paths), and `forward()`'s output dict,
then through `sam_3d_body_estimator.py`'s `process_one_image` per-person
output as `"skel_state"`. Verified by reading every call site of
`_mhr_forward_core` and `mhr_forward` in the vendored tree (`sam3d_body.py`
has two other callers; neither requests `return_skel_state`, so they're
unaffected — additive, not a signature break) and by `py_compile` on every
touched file. **Not yet run against real weights on GPU** — no Modal session
in this environment this pass. `services/motion-api/modal_app.py::export_clip_gltf`
is new, wires this into a real per-clip, per-dancer GLB export, and is
unexercised beyond `py_compile` for the same reason. This is the single
highest-priority remaining risk to close: run it for real, on a clip, and do
the literal phone check this gate has always wanted.

**2. Multi-dancer: cap 6, cost linear, no cross-dancer shortcut.**
`tools/process_clip.py` now does a detect-only pass first (cheap: RTMO +
ByteTrack, no SAM 3D Body) to decide which track ids are "confidently
tracked" (>= `CONFIDENT_MIN_FRAMES = 5` sampled frames — a plain frequency
threshold, not a learned confidence model; ponytail-flagged in the source).
If more than `MAX_DANCERS = 6` are confidently tracked, the clip is refused
**before** any reconstruction runs, so a refusal costs almost nothing. Below
the cap, every confidently-tracked dancer gets full SAM 3D Body
reconstruction — cost is linear per dancer, same per-dancer cost as the
solo-01 number above (not re-measured per-dancer this pass; see below).
**Considered and rejected (v2 idea, explicitly not built):** reconstruct one
dancer fully and use cross-dancer motion correlation to approximate the
others on synced choreography. Rejected per this work package's explicit
scope decision — full reconstruction for every confidently-tracked dancer is
simpler, doesn't assume synced choreography (which the 2026-09-18 scope
revision explicitly says is not required), and its cost is already affordable
per-clip at the solo-01 number. Recorded here so it isn't rediscovered.
`evaluation/clips.yaml`'s `violator-duet` entry (no URL, unsourced) was
renamed to `violator-crowd` and its refusal condition changed from "two
dancers doing different roles" (no longer a violation — a learner just picks
which dancer to learn from) to "more than 6 confidently-tracked dancers".

**3. Contract gap: `animation` moved from top-level to per-`PersonResult`.**
`packages/motion-contract/schema/motion-result.schema.json`: removed the
single top-level `animation: {clip_id, glb_asset_id}` (assumed exactly one
dancer) and added `animation` as a required field on each entry in `persons`
instead, so a multi-dancer `MotionResult` can say which GLB/clip belongs to
which dancer — previously there was no way to express that at all, per W5/
W6/W7's independent findings. Chose per-person over a separate `person_id`-
keyed map at the top level: every other per-person fact already lives inside
`PersonResult`, and a consumer already iterates `persons` to render each
dancer, so a second top-level collection would only be one more thing that
could drift out of sync by `person_id`. `persons` also gained `maxItems: 6`
matching the cap above. TS/Python generated types regenerated
(`npm run generate` / `bash scripts/generate-python.sh`); both test suites
(`npm test`, `uv run pytest`) pass, including the schema-validation and
invariant checks. Added `packages/motion-contract/fixtures/two-dancer-lesson.json`
— **hand-built, not a real pipeline run** (no GPU session available this
pass), but shaped to match exactly what `process_clip.py` +
`export_clip_gltf` actually produce (real ByteTrack-style track ids, one GLB
per confidently-tracked dancer, a genuine crossing-occlusion span with no
identity-continuity correction, matching this file's own documented
non-goal). Its `model_report.measured_performance` is a labeled placeholder,
not a measurement — replace it the first time this actually runs on two real
dancers.

**4. Stale doc-comment.** The schema's top-level description previously
implied exactly one dancer; updated to describe the revised multi-dancer MVP
(up to 6, 2026-09-18) and the per-person animation change.

**5. `solo-03` (turn + wrist occlusion + re-entry, the actual PRD week-one
deliverable): still has no URL. Not sourced this pass** — this environment
has no browsing/video-fetch capability and no real clip to hand-film or
download. What was tested instead: the turn case (`good-lesson.json`'s
continuous-tracking-through-a-full-turn fixture, unchanged by this pass) and
the occlusion+re-entry case (`failure-lesson.json`'s mid-playback dropout
fixture, unchanged by this pass) at the **contract level only** — these are
hand-built JSON documents, not real pipeline output on a real clip. No real
GLB was exported or viewed on a phone this pass. This gap is unchanged from
this report's original "what's left" list, item 2 above.

**6. Job-status wiring.** `tools/process_clip.py` gained an `on_progress`
callback invoked at real stage transitions (loading, extracting frames,
detecting, reconstructing, refused) with plain-language `stage_message` text
per `DESIGN.md` §7c/§7h (e.g. "Building the body — frame 40 of 296", never
"detection complete" or a bare percentage). `modal_app.py::run_clip` wires
this to write `job-status.schema.json`-compliant documents to the results
Volume as `{job_id}.job-status.json` at every real stage, not just the final
result. Not resolved in `job-status.schema.json` itself: the schema's `state`
enum has no "refused" value, only `queued/processing/succeeded/failed` — a
refusal is mapped to `state: "failed"` with `error.code: "too_many_dancers"`
and `retryable: false`, which fits the existing contract without adding a
new state. This is a judgment call, not an OPEN-DECISIONS.md item; flagging
it in case a real "refused" state is wanted later. There is no live API or
push/poll layer consuming this file yet (services/motion-api has no HTTP
server) — this writes to a Volume path a future service would read, not a
running end-to-end integration with W7's processing screen.

**What's not measured, honestly.** No Modal GPU session ran this pass (no
GPU credentials exercised, though `modal profile current` confirms an
authenticated account exists) — so there are no real multi-dancer fps/VRAM/
cost numbers to report beyond the linear-cost reasoning above, and the
`skel_state` plumbing above is verified by reading the vendored source and
`py_compile`, not by a real forward pass. Per this file's own "measure, do
not trust" standard: **do not treat the multi-dancer cost/fps numbers in
`two-dancer-lesson.json`'s `model_report` as real** — they're explicitly
labeled placeholders. The next session with GPU access should: (a) run
`export_clip_gltf` against a real `run_clip` result and check the GLB on a
phone, (b) run a real 2+ dancer clip (`group-synced-01` is already fetched)
end to end and replace the placeholder numbers, (c) source or film `solo-03`.

**OPEN-DECISIONS.md check.** Nothing in this pass required deciding an item
still marked OPEN there. The `CONFIDENT_MIN_FRAMES` threshold and the
job-status "refused → failed" mapping are implementation judgment calls
within the existing contract, not new product/design decisions of the kind
OPEN-DECISIONS.md tracks — flagged above rather than silently assumed.

---

## Export-quality addendum (2026-09-20): interpolation, frame rate, rotation

Branch `export-quality`, off `bone-constraints`. Real Modal L40S sessions ran
this pass — every number below is measured on a real exported GLB or a real
reconstruction, none is estimated.

### 1. `STEP` interpolation was the visible defect. Now `LINEAR`.

**The defect.** Every one of the 218 animation samplers in the exported GLB
carried `interpolation: "STEP"`. `STEP` means no interpolation at all: the
pose snaps to each keyframe and holds it until the next. Measured on the real
`solo-01` export by sampling 4× denser than its 15 fps keyframes: **75.4% of
rendered samples were a dead freeze**, and the body then teleported up to
**629 mm in a single sample** (p99 489 mm). That is the builder's "tracking
the movements properly, but not as crisp and pure as human movement",
quantified.

**It is not fixable at the pymomentum call.** Verified empirically against the
pinned `pymomentum-gpu==0.1.114.post0`, not assumed from docs: all three
export paths it exposes emit `STEP` — `Character.save_gltf_from_skel_states`
plain, the same call with a `FileSaveOptions`, and the lower-level
`GltfBuilder.add_skeleton_states`. `FileSaveOptions` has nine fields
(`blend_shapes`, `collisions`, `coord_system_info`, `extensions`,
`fbx_namespace`, `gltf_file_format`, `locators`, `mesh`, `permissive`) and
none concerns interpolation; every plausible keyword (`interpolation=`,
`interp=`, `linear=`, `use_linear=`, `sampler_interpolation=`) is rejected by
the pybind11 signature. So the fix is a post-export metadata rewrite
(`_rewrite_interpolation_linear` in `modal_app.py`), following the precedent
already set for post-processing an exported GLB with `pygltflib`.

**`LINEAR`, not `CUBICSPLINE` — measured, not assumed.** Held out every other
real keyframe from the `solo-01` export and reconstructed it with each mode,
scoring world joint position error in mm against the real held-out frames
(a 7.5 → 15 fps test, strictly harder than the case actually shipped):

| mode | median | p90 | p99 | max |
|---|---|---|---|---|
| `STEP` | 74.58 mm | 233.51 | 399.10 | 629.10 |
| `LINEAR` | 47.48 mm | 131.62 | 225.79 | 382.88 |
| `CUBICSPLINE` | 42.01 mm | 122.53 | 221.44 | 368.23 |

`CUBICSPLINE` buys 11% on the median over `LINEAR`. Against that it costs 3×
the animation bytes (an in- and out-tangent per keyframe), makes bone length
slightly *worse* between keyframes (18.84 mm worst vs `LINEAR`'s 18.05 mm),
and — the deciding argument — **its tangents are fabricated**. Nothing in this
pipeline measures velocity; a Catmull-Rom tangent is invented and then
rendered indistinguishably from measured data, which is exactly what
`DESIGN.md` §7h forbids. `LINEAR` adds no numbers at all: on rotations the
glTF spec defines it as slerp, and every value in the file remains one the
pipeline actually produced. **Fancier is not better here, and the measurement
is what says so.**

**Result on real hardware** (`solo-01`, `solo-07`, and a 30 fps `solo-01`
re-exported through the deployed code):

| | before | after |
|---|---|---|
| samplers `STEP` | 218 / 218 | 0 / 218 |
| frozen rendered samples | 75.4% | **1.5%** |
| largest single-sample jump | 629.10 mm | **185.07 mm** |

### 2. The `provenance.interpolated` distinction (`DESIGN.md` §7h)

A `LINEAR` sampler and `MotionResult`'s per-sample
`provenance.interpolated` are **not the same thing and must never be
conflated**. `provenance.interpolated` marks a whole pose the pipeline did not
observe and held or filled in. Sampler interpolation is how a *player* fills
the time between two keyframes, both of which are real reconstructions.
Changing `STEP` → `LINEAR` does not make any sample "interpolated" in the
contract's sense — no keyframe changed. The export manifest now records
`gltf_interpolation` as a separate field from anything provenance-related, so
the two cannot be read as one.

What §7h *does* require disclosing is this: between two real keyframes the
viewer now draws a pose that was never observed. At 15 fps with `LINEAR`
between adjacent real samples that is a defensible straight-line guess, and
§7's honesty rule is satisfied by saying so plainly rather than by refusing to
draw it — `STEP` was not more honest, it was differently wrong (it asserted
the body was *motionless* for 75% of playback, which is also a claim, and a
false one).

### 3. 15 fps vs 30 fps — evidence, not a default change

**The default is unchanged at 15 fps.** This section is the evidence for
deciding it, not a decision.

Source `solo-01` is 30 fps (576×1024, 591 frames, 19.7 s). `ffmpeg`'s
`fps=15` filter keeps every other source frame, so the 15 fps run and the
**even** frames of a 30 fps run reconstruct *the same source images*. That
gives a free control, and the whole measurement rests on it:

- **A — noise floor.** 30 fps even frames vs the 15 fps run at the same times.
  Same input pictures, so the difference is reconstruction non-determinism,
  not interpolation. Nothing below this is measurable.
- **B — interpolation error.** 30 fps **odd** frames (real reconstructions the
  interpolator never saw) vs the 15 fps run `LINEAR`-interpolated to those
  times. **This is exactly the motion interpolation fabricates rather than
  recovers.**

Interpolation was done the way a glTF viewer does it — in parent-local space,
slerp on rotations — then forward-kinematics back to world joint positions.

All 127 joints, mm:

| | median | p90 | p99 | max |
|---|---|---|---|---|
| A noise floor | 8.91 | 24.89 | 107.10 | 296.58 |
| B interpolated | 26.89 | 83.46 | 176.35 | 405.88 |
| **B − A** | **17.98** | **58.57** | **69.25** | — |

But the headline is misleading and the breakdown is the real finding: **every
one of the ten "fastest" joints in this clip is a finger or finger tip moving
at ~3.5 m/s.** A finger tip does not travel 3.5 m/s through a dance — that is
SAM 3D Body's known-weak hand reconstruction (there is a whole `hands` branch
about it), and resolving 30 fps worth of finger jitter recovers noise, not
choreography. Split by region:

| group | n | mean speed | A median | B median | B p90 | B − A median |
|---|---|---|---|---|---|---|
| **body (the choreography)** | 22 | 1.28 m/s | 4.65 mm | **16.67 mm** | 59.29 mm | **12.01 mm** |
| fingers | 44 | 3.07 m/s | 14.06 mm | 45.36 mm | 108.96 mm | 31.30 mm |
| face | 12 | 1.01 m/s | 5.55 mm | 17.31 mm | 38.30 mm | 11.76 mm |
| rig helpers | 41 | 1.47 m/s | 5.85 mm | 21.36 mm | 61.61 mm | 15.51 mm |

On the joints that carry the dance — and especially on the accents:

| body joint | speed | B median | B p90 | B max | (noise floor) |
|---|---|---|---|---|---|
| `l_wrist` | 2.61 m/s | 37.87 mm | 92.96 | 251.00 | 12.97 |
| `l_ball` (foot) | 2.48 m/s | 39.32 mm | 97.08 | 287.32 | 8.61 |
| `r_ball` (foot) | 2.45 m/s | 40.27 mm | 102.88 | 296.67 | 8.42 |
| `r_wrist` | 2.44 m/s | 38.23 mm | 87.72 | 256.25 | 13.65 |
| `l_lowarm` | 1.94 m/s | 25.56 mm | 84.82 | 165.08 | 6.49 |

Sharpest 10% of frames by peak joint acceleration: B median 41.75 mm, p90
169.73 mm, max 405.88 mm.

**The answer, in the terms the question was posed in: centimetres, not
millimetres — but only on the accents.** A wrist or a striking foot is a
median **~3.8–4.0 cm** away from where it really was, p90 ~9–10 cm, against a
noise floor under 1.4 cm. A wrist at 2.6 m/s travels 174 mm between 15 fps
samples, so a ~38 mm median error is ~22% of the travel — the path is
genuinely curved at this timescale and 15 fps is undersampling it. The
*typical* body joint, though, is only 1.2 cm off, and the whole effect is
concentrated in a minority of fast frames.

**Cost, measured on the same clip, same L40S:**

| | 15 fps | 30 fps |
|---|---|---|
| frames reconstructed | 291 / 296 | 584 / 591 |
| wall clock | ~155 s | 294.8 s |
| cost | $0.0839 | **$0.1597** (1.90×) |
| peak VRAM | 3.69 GB | 3.69 GB (unchanged) |

**Recommendation — deliberately not shipped as a default.** The evidence does
*not* support "30 fps is overkill": it recovers real, visible centimetre-scale
motion exactly where a dance lesson cares most (wrist snaps, foot strikes).
Nor does it support flipping the default blind, because the gain is confined
to fast accents, the cost is 1.90× and recurring on a free public platform,
and the `caching-retention` branch is separately adding dedupe that changes
those economics materially. This is a cost/product call with the numbers now
attached, so it is recorded in `OPEN-DECISIONS.md` (E6) rather than decided
here. Note also that VRAM does not move, so 30 fps needs no bigger GPU — only
more time.

A cheaper third option worth pricing before committing to either: the
detection pass is already the cheap one, so reconstructing at 30 fps *only*
around high-acceleration frames would buy most of the accent fidelity at well
under 1.90×. Not built, not costed — flagged, not assumed.

### 4. World-vs-local rotation bug in `api.py` — confirmed and fixed

**Confirmed independently, from the data.** `_build_motion_result` fed
`skel_state`'s quaternions straight into `_rest_relative_rotation` as though
they were already local-to-parent. They are **WORLD** rotations. The
discriminator is the bone offset — a child's position expressed in its
parent's frame is a property of the rig, so it cannot move as the dancer
moves. On the real `solo-01` reconstruction (291 frames, 127 joints):

| | q as WORLD | q as parent-relative |
|---|---|---|
| offset-vector wander / bone length, median | **0.000574** | 0.949570 |
| \|mean offset − `rest_translation`\|, median | **0.004111 m** | 0.048569 m |

The second row is checked against `joint_hierarchy`'s own `rest_translation`,
dumped independently from the FBX skeleton, which neither hypothesis can tune
itself against. Corroborating: `skel_state[:, :3]` are plainly absolute world
positions — `c_head_null` sits 1.678 m from the origin, which no local bone
offset could be. This matches `decompose()` on branch `smoothing`, which
reached the same conclusion independently (round-trips to 5.7e-14 cm); that
implementation was read rather than reinvented.

**Impact of the bug:** the rotation served differed from the correct
parent-relative one by a **median of 125.7°** (p90 168.2°, max 180.0°), with
**125 of 127 joints** off by more than 20° on average. Every joint below the
root was being served its whole chain's accumulated orientation instead of its
own bend.

**Fixed** by `_local_rotations()` in `api.py`. The root is deliberately left
alone in `root_trajectory` — it has no parent, so its world rotation *is* its
local one, and the body's world orientation is what that field asks for.
Guarded by `services/motion-api/test_api_rotations.py` (6 tests, no GPU/Modal
needed), which was itself verified to **fail** against the old behaviour — a
test that passes either way guards nothing.

**Note the GLB was never affected.** pymomentum consumes `skel_state` in its
own native format and knows it is world, so the exported animation was always
correct. This bug only ever corrupted the `MotionResult` joint rotations
served over HTTP — consistent with the mesh having looked right all along.

### 5. Frame-rate mislabelling in the export (found while fixing the above)

`export_clip_gltf` hardcoded `fps = 15.0` while `run_clip` accepts an `fps`
argument. Any non-default run was therefore exported with the wrong timing —
the 30 fps reconstruction above would have shipped as a 15 fps animation,
i.e. **playing at half speed**. Now derived from the npz's own
`sample_times_s` spacing, which also keeps a standalone re-export correct
without threading a parameter that could disagree with the data it describes.
Verified on hardware: the 30 fps clip exported as `30.0 fps (591 samples)`,
`solo-01` and `solo-07` as `15.0 fps`.

### 6. Verification on real hardware

`solo-01`, `solo-07` and the 30 fps `solo-01` re-exported through the deployed
code, then checked locally against the downloaded GLBs:

- **interpolation** — 218/218 samplers `LINEAR` on `solo-01` and `solo-07`
  track 1, 218/218 on the 30 fps export, and 213–216/213–216 on `solo-07`'s
  three partially-observed tracks. Zero `STEP` remaining, across 8 GLBs.
- **non-finite values — zero**, in all of them. The NaN-frame-0 guard in
  `export_clip_gltf` is untouched and still raises before writing; the rewrite
  adds its own independent finite check afterwards, so a GLB that would render
  as nothing now has to get past two separate guards.
- **bone lengths survive exactly.** The rewrite is metadata-only and this was
  verified rather than asserted: the GLB's **binary chunk is byte-identical**
  before and after (same length, `==` on the bytes), and max keyframe delta is
  exactly `0.000e+00` on translation, rotation and scale. Bone-length CV at
  the keyframes is therefore unchanged to the last digit — median `9.983e-07`,
  max `6.692e-06` (0.0007%), worst absolute spread over the whole clip
  **0.000855 mm**. The `bone-constraints` result is intact.

**A real caveat found, and it is not caused by this work.** `solo-07`'s npz on
the results Volume was **stale — reconstructed before `bone-constraints`
landed**: measured directly on the npz's own world positions, its bone CV was
19.54% (median 1.84%), versus 0.0003% for `solo-01` and 0.0003% for the 30 fps
run made today. The export faithfully carried that through, which is correct
behaviour, but anyone reading an old `solo-07` GLB as evidence of bone
rigidity would have been misled.

Re-run through the full current pipeline this pass (`run_clip` → chained
`export_clip_gltf`, which also exercises the whole fixed chain end to end
rather than just the export stage in isolation). After: bone CV **0.0004%,
0.0003%, 0.0004%, 0.0005%** on its four tracks — the defect was entirely the
stale artifact. The refreshed `solo-07` track 1 GLB is `LINEAR`, zero
non-finite, bone CV 0.0007%, worst absolute spread 0.001046 mm.

Worth recording as a general hazard: **the results Volume mixes artifacts from
different code generations and nothing in a `.npz` records which.** A
`pipeline_git_sha` in the npz would make this self-diagnosing; `model_report`
already carries one in the contract, but it is hardcoded in `api.py` rather
than captured at reconstruction time, so it does not currently help.

### 7. Known, measured, disclosed cost of `LINEAR`

pymomentum carries part of some joints' bone *direction* in the translation
channel rather than in the parent's rotation — `l_index1`'s local offset
swings **79° between adjacent keyframes** while its length stays constant to
six decimal places. Lerping a direction takes the chord, so those bones
shorten transiently *between* keyframes: median 0.00006 mm, p90 0.44 mm, but
up to **18 mm (23% of its length) on a finger**. It is exact again at every
keyframe, and `CUBICSPLINE` is marginally worse (18.84 mm), so this is not an
argument for the other mode.

glTF has no "slerp the translation" mode, so the only real fix is re-deriving
the local decomposition so bone direction lives in the rotation channel — a
change to the export itself, not to a sampler attribute. Recorded in
`OPEN-DECISIONS.md` (E7) rather than guessed at here. In practice it lands on
finger bones, which this pipeline already reconstructs badly (see the fps
breakdown above and the `hands` branch).

### 8. What's still not measured

- **No phone check.** Every number here is geometric, measured on the GLB and
  the reconstruction. Whether the result *reads* as crisp human movement on a
  real device is still unverified by this pass — the builder's "mesh 3d
  looking much more smooth now" on a hand-patched file is the only
  human-perception evidence, and it is not a measurement.
- **One clip carries the fps conclusion.** The 15-vs-30 numbers are `solo-01`
  only. A slower or faster dance would move them; a second clip would cost
  ~$0.16 and has not been spent.
- **The hybrid adaptive-rate option is unpriced** (§3).
- **`group-synced-01` was not re-exported** this pass, so multi-dancer GLBs on
  the Volume still predate these fixes.
