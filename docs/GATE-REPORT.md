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

## Hands addendum (2026-09-18, branch `hands`)

The PRD (§5, §9) and `evaluation/clips.yaml`'s `stress-hands` entry both
*assumed* articulated hands would be unreliable and a video crop would be the
right answer. This pass measured it instead of assuming it, on the real
`solo-01.npz` / `solo-07.npz` in `stepwise-results` and the matching 576x1024
clips in `stepwise-eval`. The assumption was right, but two of the reasons
given for it were wrong, which matters for when to revisit.

### 1. Do MHR's existing finger channels carry hand shape? Measured: barely.

`skel_state`'s quaternion block is the joint's **global** rotation — it
converts to `pred_global_rots` with max abs difference 6e-8. Raw per-frame
deltas on those channels therefore show finger joints "moving" ~34 deg/frame,
which is the wrist carrying them, not articulation. Composing with the parent's
inverse first gives the real picture — full angular span of each joint's
local rotation over a whole clip:

| joint | solo-01 t4 (291 f) | solo-07 t1 (353 f) |
|---|---|---|
| shoulder | 170 deg | 137 deg |
| elbow | 146 deg | 132 deg |
| knee | 125 deg | 147 deg |
| wrist | 80 deg | 94 deg |
| **finger knuckles (30)** | **23 deg median, 42 max** | **22 deg median, 33 max** |

Open hand to fist is ~90 deg at every knuckle. The fingers explore about a
quarter of that and reach neither end. Per-frame jitter (2.6 deg) is the same
order as the entire clip's variation (3.7 deg): this is wobble about a fixed
mean hand pose, not motion.

### 2. Is it a prior, or weak evidence? Measured: weak evidence.

Compared against an independent 2D hand landmarker run over the estimator's own
hand crops from the real footage, using scale/rotation-free descriptors:

- Whole-hand shape (Procrustes RMS): **0.889 / 0.984 on matched frames vs
  0.939 / 0.982 on deliberately shuffled frame pairs.** Indistinguishable from
  no relationship at all.
- Per-finger curl correlation: **r = +0.30 to +0.49** (shuffled-null p95 ~0.10).
  Real, but ~16% of variance.
- MHR's curl never drops below 0.50 (1.0 = straight); the landmarker's reaches
  0.23. **MHR does not make fists.**

### 3. Would a dedicated hand model fix it? Measured: no, and not for the
reason the PRD gave.

The `clips.yaml` RESOLUTION FINDING estimated 15-20 px per hand. Measured, the
hand is bigger than that: the estimator's hand crop is **median 121 px
(solo-01) / 110 px (solo-07)**, with the hand's own reprojected span ~38 px.
Resolution is not the binding constraint. What is:

| hand crop px | landmarker detection rate | its own frame-to-frame curl jump | wrong-hand label rate |
|---|---|---|---|
| 0-60 | 34.5% | 0.242 | 20.4% |
| 60-90 | 64.8% | 0.068 | 34.3% |
| 90-120 | 67.4% | 0.188 | 24.5% |
| 120-160 | 70.6% | 0.182 | 22.5% |
| 160-220 | 90.3% | 0.086 | 28.2% |

Its own jitter (0.14-0.18) is more than half its entire spread (0.26), and it
mislabels which hand it is looking at in 20-34% of crops **at every size**. That
is motion blur and source compression, not pixel count, so more pixels alone
does not fix it. Retargeting that onto MHR's finger chains would trade a flat
wrong hand for a jittery, sometimes-mirrored wrong hand — the exact "confident
wrong hand shape" failure `DESIGN.md` §7h forbids. **No hand model was added.**

### 4. What shipped instead

- `crop_rects.hands` and `.feet` populated from the **detector's** wrist/ankle
  keypoints (MHR's reprojected ankles are 51.8 px / p90 106 px off the
  detector's on solo-01 — a crop built from them misses the foot).
- A per-hand `hand_confidence` capped at **0.25**, the measured ceiling
  (r^2 ~ 0.09-0.24). Measured output: mean 0.046, max 0.20; both hands at zero
  confidence on 37% of reconstructed frames. Any sane suppression threshold
  renders hands `uncertain`, which is the correct product outcome.

### 5. What is still missing

`stress-hands` has no sourced footage and this work could not validate against
it. What it needs, concretely: a clip with **deliberate, held, distinguishable
hand shapes** (fist / flat palm / point / two-finger), filmed **at 1080p or
better** so the hand crop lands above 200 px, **front-on**, with the shapes held
for at least ~0.5 s so per-frame blur is not the dominant error. The builder's
own dance school is the realistic source, and it also solves the `rights:`
problem that blocks every scraped clip. Until such a clip exists, "hands are
unreliable" is measured on incidental hand poses only — nobody in solo-01 or
solo-07 is deliberately making a shape.

**Revisit trigger, stated so it is falsifiable:** re-open the hand-model
question when a candidate's per-finger curl correlates **r > 0.8** with
independent evidence on real footage *and* its own frame-to-frame jitter is
below a quarter of its spread. Neither is close today.

**OPEN-DECISIONS.md check.** Nothing here required deciding an item still
marked OPEN. `MAX_CROP_FRAME_FRAC` (when two hands can no longer share the
contract's single `hands` rect) and `HAND_POSE_CEILING` are measured
implementation thresholds inside the frozen contract, not new product
decisions — both are documented with their measurements in
`tools/hand_crops.py` rather than silently assumed. E2 (the uncertain-limb
render) is unaffected but now has a concrete worst case to design against:
hands are `uncertain` essentially always.

### 6. Four-axis licence read on the one candidate evaluated

`docs/research/grounding-models.md` is not on this branch, but its method is:
check **code licence, weights licence, assets required at inference, and
training-data terms**, from the actual files, not the README. MediaPipe Hands
(`hand_landmarker`) was the obvious candidate and was the tool used for the
independent measurements above. It is **not adopted and not a dependency of
anything in this repo** — it was run locally as a measuring instrument only.
Had it been adopted, this is what the four axes say:

| Axis | Verdict | Evidence |
|---|---|---|
| Code licence | **Apache-2.0, clean.** | `mediapipe-1.0.1.dist-info/licenses/LICENSE` is the verbatim Apache 2.0 text; `License-File: LICENSE` in METADATA. |
| Weights licence | **NOT ESTABLISHED.** | The `hand_landmarker.task` bundle contains exactly two files, `hand_detector.tflite` and `hand_landmarks_detector.tflite`, and **zero licence strings anywhere in either** (grepped the raw bytes). The task page states a licence only for the documentation and code samples, not the bundle. The commonly-cited "Apache-2.0 weights" comes from third-party mirrors. Upstream issue google-ai-edge/mediapipe#6355 is an open request for exactly this artifact-bound licence/provenance record. This is the Depth-Anything-V2 pattern the grounding survey warned about: permissive repo, unstated weights. |
| Assets at inference | **Fetched from Google at runtime, not vendored.** | The wheel bundles no model; the `.task` comes from `storage.googleapis.com/mediapipe-models/...`. A shipping pipeline would have to vendor and pin it, which is precisely the act the unstated weights licence does not authorise. |
| Training-data terms | **Unverifiable.** | Published description is ~30K images: a 6K in-the-wild set, an **in-house collected 10K gesture set**, and synthetic renders. The in-house set's collection and consent terms are not published — and `docs/OPEN-DECISIONS.md` D8 already makes consent-to-process a live obligation for this product. |

One extra obligation that would have applied and is easy to miss, found in the
distributed `NOTICE` rather than any README: *"MediaPipe Tasks APIs send metrics
about the performance and utilization of the APIs in your app to Google... You
are responsible for obtaining informed consent from your app users about
Google's processing of MediaPipe metrics data as required by applicable law."*

**Verdict: disqualified on axis 2 alone, independently of the measurements.**
Even if the finger pose had improved, the weights could not be shipped on
today's published terms. The measurements above mean that question does not
arise.
