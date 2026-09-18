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

## Shape addendum (2026-09-18): the estimated body shape now reaches the GLB

Branch `shape-params` off `w4-jobservice`. Every number below was measured on
real Modal hardware against the real `solo-01.npz` and the real exported GLBs —
nothing here is reasoned from the source alone.

**The bug.** `SAM3DBodyEstimator.process_one_image` returns `shape_params` (45)
and `scale_params` (28) per person per frame, `process_clip.py` saves them into
the npz, and `export_clip_gltf` then built its character with
`Character.load_fbx(lod3.fbx)` and drove it with `skel_state` only. The 45-dim
shape estimate was never applied, so every dancer was exported with the mean
MHR body.

**How shape is baked (there is no "apply shape" call in pymomentum).**
`pymomentum-gpu==0.1.114.post0` exposes `Character.with_blend_shape()`, but that
attaches a basis for the *solver* to drive through model parameters, and the
only export entry point, `Character.save_gltf_from_skel_states(path, character,
fps, skel_states)`, has no parameter channel to carry shape. The supported route
is to bake the displacement into the character's rest mesh, which is exactly
MHR's own two-stage pipeline (shape → rest verts → LBS), verified rather than
assumed:

- `mhr_model.pt` buffers `character_torch.blend_shape.base_shape` (18439, 3) and
  `.shape_vectors` (45, 18439, 3) reproduce the model's own forward shape path
  to **3.8e-5 cm**, so no guess about the 204-dim `model_parameters` layout is
  needed. `base_shape` equals the zero-parameter forward output to 4.6e-5 cm.
- Shape moves **only the mesh**: at shape=0 vs shape=median the rest joint
  positions differ by 0.0000 cm and the `skel_state` scale column stays 1.0000.
  Baking into the rest mesh therefore cannot conflict with the per-frame pose.
- The shipped LOD is decimated (lod3: 4899 verts, lod4: 2461; only these two are
  in the `stepwise-weights` Volume) while the basis is on the 18439-vert mesh.
  Both are the same body in the same rest pose and units (cm): lod3's vertices
  sit **0.2957 cm mean / 1.79 max** off the full-res surface. The shape
  displacement is transferred by nearest full-res vertex, and the transfer was
  validated in rest space where no alignment is needed:

  | lod3 rest mesh → nearest point on | mean | max |
  |---|---|---|
  | MHR neutral surface (decimation floor) | 0.2972 cm | 1.79 cm |
  | MHR **shaped** surface, shape ignored (the bug) | 0.3904 cm | 2.33 cm |
  | MHR **shaped** surface, after transfer | 0.2959 cm | 1.66 cm |

  i.e. the transfer puts the LOD back on the estimated body to within the
  decimation floor. A guard in `export_clip_gltf` refuses to export if that
  nearest-neighbour mean ever exceeds 1.0 cm (mismatched asset or unit change).

**Averaging: per-dim median, not mean.** Body shape is constant, so 291
per-frame estimates are repeat measurements of one value, and they are noisy:
per-dim std 0.199 mean / 0.459 max, per-frame L2 distance from the mean 1.42
mean / 2.99 max against `||mean|| = 2.883` — the frame-to-frame scatter is about
half the vector's own length, so averaging is doing real work (frame 0 alone
would have been a coin flip). On this clip the estimator has no gross outliers:
`||mean − median|| = 0.121` (4.2%) and `||mean − trimmed10%|| = 0.062`, so the
three estimators agree. The median is used anyway: it costs the same, bounds any
single partial-view or occluded frame's influence, and `solo-01` is the clean
baseline clip — the frames this has to survive are on clips not yet run.

**Measured effect, before → after (`solo-01`, track 4, 291/296 observed).**
Same 4899 verts / 9794 tris / 206 nodes / 296 keyframes / 1,528,348 bytes:

| | before | after |
|---|---|---|
| non-finite animation values (total / at frame 0) | 0 / 0 | **0 / 0** |
| rest-mesh vertices moved > 0.1 mm | — | 67.3% |
| rest-vertex displacement | — | mean 0.249 cm, median 0.086 cm, p99 1.88 cm, max 2.135 cm |
| rest bbox span (m) | [1.30611, 1.72541, 0.39364] | [1.30611, 1.72920, 0.38405] |
| chest slab depth (z span, y∈[1.2,1.4]) | 28.21 cm | 25.00 cm (−11.4%) |
| hip slab depth (z span, y∈[0.9,1.1]) | 39.36 cm | 38.41 cm (−2.4%) |
| vertex normals | — | recomputed; mean 1.29°, max 17.3° change |
| animation channels (221,408 sampled values) | — | **max abs difference 0.000e+00** |

The animation is bit-identical, which is the point: only the body changed. The
GLB was re-loaded with trimesh (a third-party loader, not our own parser):
4899 verts, 9794 faces, all finite, watertight. The NaN-frame-0 guard from
`fix(export): NaN frame 0` is untouched and still passes — for contrast, the
stale pre-fix `solo-01_track1.glb` still on the Volume has **384 non-finite
values, all at frame 0**, which is what that bug looked like.

**What this does NOT fix, stated plainly.** MHR's shape basis is a surface
corrective: at this dancer's estimated shape it displaces the mesh 2.5 mm on
average (2.1 cm max), and even a +3.0 on all 45 dimensions only reaches 1.4 cm
mean / 13.2 cm max. Body *size* — limb lengths and overall scale — comes from
the 28 `scale_params`, which are already inside the per-frame `skel_state` that
was always exported (its scale column averages 0.9716, min 0.8925, so the
skeleton is already dancer-scaled). So `scale_params` are deliberately **not**
re-applied here: averaging and re-applying them on top of `skel_state` would
double-count.

That the GLB really carries them was checked rather than assumed, because the
exporter writes only **2 scale channels for 127 joints** (97 rotation, 118
translation), which looked like dropped size. It is not: replaying the GLB's own
TRS animation down its node hierarchy at frame 100 reproduces the estimator's
joint world positions to **1e-4 cm** and every bone longer than 5 cm to
**0.0000 cm**, and skinning the GLB with its own joints/weights/inverse-bind
matrices matches `pymomentum.skin_points` on the same frame to **1e-4 cm**
(identical bounding box, 98.701 × 140.229 × 98.662 cm) even though 46 joints
have a scale below 0.99 there. The exporter folds joint scale into the
transforms it writes; nothing is lost.

That leaves a real, separate defect this pass did not fix and did not hide:
because scale is re-estimated every frame, **bone lengths wobble frame to
frame** — over the 291 observed frames, 65 bones longer than 5 cm have a
coefficient of variation of 8.99% on average and 24.57% at worst (femur 42.29 cm
± 1.51, foot 39.41 cm ± 1.75). A body does not change length while dancing, so
a constant-size fit (averaged scale, per-frame pose) is the honest fix. It is
not attempted here because it needs the MHR forward re-run with averaged scale
plus per-frame pose, and the estimator does not expose the 204-dim
`model_parameters` layout those would have to be packed into — inverting it by
guess is exactly the "silently produces a warped mesh, not an error" failure
this report exists to avoid. Flagged for a future pass, with the numbers above.

**Contract.** No schema change. `MotionResult.persons[].shape_params` already
means "one vector for the whole clip, estimated from well-observed frames"; the
export now writes the exact baked vector into `{clip_id}.export-manifest.json`
and `api.py` serves that instead of the first observed frame's sample, so the
contract and the mesh can no longer disagree. The per-frame fallback remains for
GLBs exported before this change.

**OPEN-DECISIONS.md check.** Nothing here required deciding an item marked OPEN
there. The frame-to-frame bone-length wobble above is a new measured finding,
not one of its entries — reported, not silently assumed away.
