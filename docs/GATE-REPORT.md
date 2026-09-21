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
## Grounding addendum (2026-09-18): the floor solve, and why it says `none`

Branch `grounding` off `w4-jobservice`. Real Modal GPU session this pass:
`solo-07` (the `floor-work` clip) was run end to end for the first time, and
`solo-01`'s existing npz was re-read. Every number below is measured.

**Reproducibility note.** `solo-01` was re-run end to end on current code at
the end of this pass (its stored npz predated W4 and had no frame size). The
floor numbers reproduce to the digit — floor 0.0529 m, RMS 0.01454, planted
fraction 0.1607, tilt 9.18° vs 9.20° — off a fresh reconstruction, so none of
this is an artefact of one stale run. Note the ByteTrack id changed (4 → 1)
between runs; nothing in the solve depends on it.

**What was built.** `services/motion-api/grounding.py` — two deliberately
separate, independently replaceable functions plus the honesty decision around
them, wired into `api.py::_build_motion_result` in place of the hardcoded
`{"status": "none", "floor_plane": null}`. 13 tests in
`services/motion-api/test_grounding.py`, no GPU needed.

**The measured result: both real clips honestly report `none`.** Not because
the solve failed — it fits a tight plane on both — but because of what the
plane turns out to describe.

| | solo-01 (baseline) | solo-07 (floor work) |
|---|---|---|
| reconstructed frames | 291 / 296 | 436 (4 track ids) |
| both feet visible | 96.2% | 97.9% |
| contact candidates → inliers | 39 → 27 | 222 → 192 |
| inlier RMS | **1.45 cm** | **1.25 cm** |
| fitted floor height | 0.053 m | 0.109 m |
| fitted tilt from +Y | 9.2° | 10.5° |
| contact evidence covers | **7 of 20 s (0.35)** | **12 of 24 s (0.50)** |
| lowest foot's median gap to that plane | **0.125 m** | **0.578 m** |
| frames with a foot within 3 cm of it | 16.1% | 28.1% |
| verdict | `none` (`contacts_not_spread_over_clip`) | `none` (same) |

**Root cause, and it is structural, not statistical.** `skel_state`'s root
translation is **constant for every frame of every clip** — `(0, 92.399, 0)` cm
on solo-01, all 291 frames — and `body_world` is identity. So in the only frame
the renderer and the pipeline share (the exported GLB's), the pelvis is pinned
at a fixed height and the vertical datum rides the body: a plié lifts the whole
skeleton off its own floor. Confirmed against an independent observable: the
reconstruction's lowest-foot height correlates **-0.52** with the detector's
image-space ankle position on solo-01 (i.e. when the model says the foot went
up, the video says it went down) and **-0.89** with detector bbox height on
solo-07 — the "float" tracks the crop box, not the dancer.

**The obvious fix was tried and measured worse.** Placing the body on its own
view ray at a clip-constant depth (`pred_cam_t * Z0/z`, justified by the MVP's
static-camera assumption) widens the lowest-quartile spread of the floor
estimate from 0.117 m to 0.284 m on solo-01 and 0.174 m to 0.210 m on solo-07.
Raw `pred_cam_t` is worse still: its z swings 3.18→10.93 m on solo-01 and
correlates -0.93 with bbox height, putting every foot point on one viewing ray
(y/z correlation 0.98) — a degenerate configuration for plane fitting. **The
character-local frame is the best vertical datum currently available, and it is
still not good enough for a whole clip.**

**The solve is not merely cautious.** On solo-01 frames 0–45 (3.0 s, dancer
upright, pelvis near canonical height) it returns `grounded`: floor at 0.038 m,
1.22 cm RMS, 5.3° tilt, coverage 0.67, and the lowest foot within 3 cm of the
plane in 47.5% of frames with a 3.4 cm median gap. That document validates
against the frozen contract. The gate is discriminating, not refusing.

**What this blocks.** Grounding cannot become `grounded` for a whole real clip
until the pipeline produces a per-frame global vertical placement for the body
(see `docs/OPEN-DECISIONS.md` E6). Until then, every lesson renders floorless,
which makes `OPEN-DECISIONS.md` B3 (what a floating body actually looks like)
the live design question rather than an edge case.

### World placement (the dancer travelling): investigated, not shipped, and why

Asked during this pass, because the builder's complaint is real: *"the
simulation just looks like it's always centered... in the actual video the
dancer might be moving around the stage... jumping from one place to another."*
He is right about the symptom. `root_trajectory` is exactly `(0, 0.924, 0)` on
**all 291** solo-01 frames — zero range on every axis. The dancer dances in
place.

The reasoning for why it should now be tractable is sound as far as it goes:
the camera is static by contract (`Camera.model` is `"pinhole"` const, one
camera per clip), so there is no SLAM problem, and a known ground plane plus
feet in contact should pin the depth. Three things were measured before
accepting that, and they say don't ship it.

**1. The floor constraint alone does not make it well-posed.** With per-frame
depth `d_f` unknown *and* the plane `(n, c)` unknown, each contact frame
contributes one equation and one unknown: `n·(jc_foot + d_f·r_f) = c`. The
plane's three degrees of freedom stay free no matter how many contacts there
are. Any plane admits a consistent set of depths. The missing constraint has to
come from the body's metric size interacting with perspective — i.e. from the
reconstruction, not from the floor.

**2. So the reconstruction was tested directly, and it is what fails.** An
independent full-frame PnP (the model's metric body `jc`, the *detector's*
COCO-17 keypoints as observations — not the model's own, which are its fit by
construction — under the exact pinhole model, 3-DoF Gauss-Newton per frame):

| | model `pred_cam_t.z` | independent PnP `t.z` | agreement |
|---|---|---|---|
| solo-01 | 3.18–10.93 m (range **7.75 m**) | 2.85–10.95 m (range **8.10 m**) | **r = +0.983** |
| solo-07 | 3.49–7.34 m (range 3.85 m) | 3.24–4.66 m (range **1.41 m**) | r = +0.393 |

On solo-01 the independent solve *agrees* with the model: given this
reconstruction, the dancer really does recede 8 m. So the swing is not a
weak-perspective artefact that better camera fitting removes — the per-frame
body itself is inconsistent with a dancer standing in one place. (Two cheaper
fixes were tried first and both failed: rescaling every frame to a common
metric body size, which is reprojection-preserving and therefore cannot
contradict the image, moved solo-01's depth range only 7.75 → 7.80 m; placing
the body on its own view ray at a clip-constant depth widened the floor
estimate's lowest-quartile spread from 0.117 m to 0.284 m.)

**3. The raw image says the dancer does not move like that.** Over solo-01 the
detector bbox *bottom* stays at 779–894 px while its *top* swings 215–631 px.
Feet planted, head dropping — a dancer getting low in one spot. Walking 8 m
away would raise the feet in frame, and it does not happen. No cuts either
(largest frame-to-frame bbox change is 82 px across smooth ramps). The
reconstruction is turning "got low" into "moved away", which is also the same
root cause as the grounding drift above, seen from the other side.

**Decision: leave the dancer pinned, honestly.** Composing `pred_cam_t` would
make the dancer slide metres backwards every time they crouch, and land jumps
wherever the bbox happened to be — the §7h failure applied to trajectory, and
the most visible kind. Pinned-in-place is a visible limitation; sliding is a
confident lie. Same rule, same answer as the floor.

**What a follow-on gets, so nothing is re-derived:**

- **Verified projection model.** `u = fx·X/Z + cx`, `v = fy·Y/Z + cy` with the
  principal point at the **image centre** reproduces `pred_keypoints_2d` from
  `pred_keypoints_3d + pred_cam_t` at **0.00 px** median error on real solo-07
  output. The obvious wrong guess, the crop bbox centre, gives 277.78 px.
- **Real intrinsics, now in the contract.** `focal_length` in the npz is the
  pipeline's own FOV estimate and is *exactly* constant per clip (one unique
  value across all 291 solo-01 / 436 solo-07 person records): 1174.88 px on
  solo-01, 1173.14 px on solo-07. `api.py` emitted a self-described placeholder
  (`fx = fy = max(w, h)`) that was 12.8% low; it now emits the measured value
  via `grounding.camera_intrinsics_from_clip`.
- **`GroundingResult.evidence`**, populated *even when the verdict is `none`*:
  the fitted `PlaneFit` (normal, point, inliers, RMS, tilt), per-track per-frame
  per-foot contact weights, the contact points they refer to, and the foot
  visibility mask. A refused plane is refused as a product claim, not as a
  number.
- **Camera height and tilt:** tilt relative to the body frame is measurable
  (9.2° on solo-01, 10.5° on solo-07, from the fitted normal). Camera *height*
  is not recoverable without trustworthy depth, so it is not reported rather
  than guessed.

**`camera_to_world` stays identity**, and that is a statement, not laziness:
this document's "world space" IS the exported GLB's character-local frame,
which is what `root_trajectory` and `grounding.floor_plane` are both expressed
in, so the document is self-consistent. Writing a real camera extrinsic while
the body is still pinned at the origin would make it internally inconsistent,
not more truthful.
## W9 addendum (2026-09-18): temporal smoothing + suppression

Branch `smoothing`, off `w4-jobservice`. New module
`services/motion-api/vendor/fast-sam-3d-body/tools/smoothing.py` (pure
functions over per-frame arrays), its self-check `tools/test_smoothing.py`,
and the verification harness `evaluation/measure_smoothing.py`. Wiring into
`tools/process_clip.py` is one call plus the npz key. Every number below was
measured by running the shipped code path against real `run_clip` output
pulled from the `stepwise-results` Volume (`solo-01.npz`, `solo-07.npz`) —
CPU only, no GPU session this pass.

**1. The headline finding, which changed the design: most of the measured
"jitter" is the dance.** The W9 brief's defect numbers are real and
reproduce exactly (solo-01, 291 frames, 127 joints: per-frame mean joint
displacement 0.1088 m, p90 0.1704, per-frame max single-joint 0.2692 m
mean / 0.5831 m worst = 8.7 m/s). But a spectrum of the same world joint
positions says **97% of the power is below 3 Hz, 1.1% above 5 Hz, and the
flat-extrapolated white-noise share is ~0.1%**. Human voluntary limb motion
is band-limited around 5 Hz, so at a 15 fps sample there is almost no
high-frequency noise available to remove. Two independent noise estimators
agree on the measurement noise floor — third-difference MAD and the 6–7.5 Hz
PSD level, 2–5° per frame on real limb joints, median disagreement 12%
(p90 29%) across the 163 of 381 joint-axes that have a noise floor above the
model's floor at all; the other 218 are MHR's procedural twist/tongue/eye
joints, whose local rotation is a deterministic function and genuinely does
not jitter.

This was not assumed, it was learned the hard way: an intermediate version
of this module did drive mean jitter down 43.8% — and took **41% of the
sub-3 Hz motion with it**, flattening accent peaks to 55% of their raw
height. That version is why the module now carries explicit spectral and
accent checks rather than a jitter number alone.

**2. Smoothing: 384 independent FilterPy constant-velocity filters, and how
rotations are handled.** One filter per unwrapped scalar, per
`docs/PRD.md` §4: three per joint for rotation, three for the root's world
translation. Quaternion components are never filtered as scalars. Instead
each joint's *local, parent-relative* rotation is filtered in the tangent
space of the filter's own nominal quaternion — the measurement handed to the
filters is `z = log(q_nom⁻¹ · q_meas)`, three genuinely independent,
structurally-unwrapped angles, and the filtered result is injected back
multiplicatively (`q_nom · exp(δθ)`), so the output is a unit quaternion by
construction and the q/−q hemisphere flip is invisible to the filter. There
is a self-check for exactly that: flipping the sign of the input
quaternions on 15 of 40 frames moves the resulting body by < 1e-6 m.

Working in parent-local space needs forward kinematics, which is also where
the skel_state format got pinned down empirically: `decompose → recompose`
round-trips solo-01 to **5.7e-14 cm** in float64, and dividing by the
*parent's* scale drops median bone-length variation from CV 0.015 to CV
0.005 — that is the evidence that a momentum skel_state row is a joint's
**world** transform composed as `p_child = p_parent + s_parent · R_parent ·
offset`, not a local one.

**3. Parameters, and the lag/sharpness trade.** R (measurement noise) and Q
(process noise) are both measured per joint per axis from the clip itself,
not hand-tuned: R from the third-difference noise floor, Q from the clip's
own robust angular-acceleration scale. The steady-state gain that falls out
is K ≈ 0.76 median (p10 0.61, p90 0.84) on the joint-axes that carry real
noise, which — independently — is the gain whose first-order equivalent puts
its −3 dB corner at **~5 Hz**, the top of human voluntary movement.
Two different arguments, one filter. A constant-velocity model has *zero*
steady-state lag on constant-velocity motion by construction; it lags only
against acceleration, i.e. only at an accent, which is why it was chosen
over the smoother everyone reaches for. Measured against that strawman
(a centred moving average tuned to remove the *same* amount of jitter):

| | Kalman + suppression | moving average, same jitter |
|---|---|---|
| accent peak speed retained (solo-01, 26 accents) | **95.4%** (worst 73.5%) | 68.6% (worst 29.6%) |
| accent peak speed retained (solo-07, 31 accents) | **96.7%** (worst 46.5%) | 71.1% (worst 8.6%) |
| timing lag | **0 frames** | 0–1 frames |
| 0–3 Hz power kept (solo-01) | **101.1%** | 93.1% |
| 5–7.5 Hz power kept (solo-01) | 82.1% | 25.4% |
| 5–7.5 Hz power kept (solo-07) | 46.2% | 9.3% |

Accents were located as local maxima of a median-filtered body-speed curve,
so the noise the smoother is meant to remove cannot define its own target.

**4. Jitter, before and after.** Small on solo-01 by design (see item 1) and
larger on solo-07, which genuinely is noisier:

| metric (world joint positions) | solo-01 raw → smoothed | solo-07 raw → smoothed |
|---|---|---|
| per-frame mean displacement | 0.1088 → **0.1034 m** (−5.0%) | 0.0675 → **0.0602 m** (−10.8%) |
| per-frame mean, p90 | 0.1704 → 0.1622 (−4.8%) | 0.1294 → 0.1127 (−12.9%) |
| per-frame max single-joint, mean | 0.2692 → 0.2658 (−1.3%) | 0.1818 → 0.1612 (−11.3%) |
| per-frame max single-joint, p99 | 0.5683 → 0.6480 (+14.0%) | 0.7659 → 0.5290 (−30.9%) |
| worst single-joint speed | 8.75 → 10.68 m/s | **14.61 → 10.49 m/s** (−28.2%) |

The solo-01 tail going *up* is real and is explained, not hidden: a
suppressed block holds its pose, and the frame where it re-acquires moves
further than one frame's worth. Every such sample is flagged `uncertain` —
over only the samples the result still **claims** as observed, solo-01 goes
0.1047 → 0.1018 m mean and 0.5620 → 0.6225 m worst, solo-07 goes 0.0619 →
0.0553 m mean and 0.5629 → 0.5219 m worst. Both numbers are reported by
`evaluation/measure_smoothing.py`; neither is the one to quote alone.

**5. Suppression — what got marked, and why.** Three inputs, never one:

* **Detector evidence per region.** RTMO's 17 COCO keypoints are mapped onto
  MHR's 127 joints by nearest anchored ancestor, so a suppressed wrist
  suppresses all 22 joints of that hand (`docs/PRD.md` §4's conservative
  region mapping). Confidence below 0.3 → `uncertain` / `low_confidence`;
  a keypoint predicted outside the frame → `absent` / `out_of_frame`.
  Measured on solo-01: RTMO's scores are strongly bimodal (median 0.98–1.00
  when visible, below 0.1 when not), so the threshold sits in a dead zone —
  anything in 0.2–0.5 gives the same answer.
* **Physical plausibility of the measurement itself**, computed from the
  estimator's output only, never from the filter's state: rejected if the
  joint's world speed exceeds 8 m/s averaged over a 67 ms sample (past the
  fastest hand speeds ever measured on a human, 9–11 m/s in a punch or a
  throw) or its implied acceleration exceeds 150 m/s² ≈ 15 g (the top of
  measured peak segment accelerations in sport; choreography is well below).
* **Optional upstream correction magnitude.** If the `bone-constraints`
  module lands and reports how far it had to move a joint, large corrections
  become `low_confidence`. Optional by design — nothing here depends on that
  branch.

Then: conservative propagation to descendants, and hysteresis (degrade
immediately, recover after 3 clean frames).

solo-01 (37,592 joint-samples = 296 frames × 127 joints):

| | count | share |
|---|---|---|
| `observed` | 33,751 | 89.8% |
| `uncertain` (`low_confidence`) | 2,793 | 7.4% |
| `absent` (`out_of_frame`) | 1,048 | 2.8% |
| of which: measurements rejected as physically impossible | 69 | 0.18% |
| filter updates refused by the per-block gate | 15 | — |
| filter updates skipped because the detector could not see the region | 1,529 | — |

The uncertain mass is concentrated where it should be: the fingers of
whichever hand the wrist keypoint lost (l_index/l_thumb chains, ~50 frames
each) and the face during the back-turn — which is `uncertain`, never
`absent`, per §7h case 1. solo-07 (44,958 joint-samples): 95.2% observed,
4.8% uncertain, 0 absent, 268 physically-impossible samples.

Its four tracks also exercise the honest end of the scale: tracks 5 and 9
were reconstructed on 21 and 14 of 354 frames, and come back 98% `uncertain`
— today the exporter's forward-hold presents those same frames as a
confident frozen body with no flag at all.

**6. Skipping suppressed blocks, and the two things that broke first.** A
suppressed block does not predict and does not update — it holds its last
filtered pose, and after 0.2 s without evidence it restarts cold at its next
real measurement. Both of those are the result of a measurement, not taste:

* Coasting on the constant-velocity prediction through a gap (the textbook
  answer) let joints with a real 25 rad/s angular velocity extrapolate up to
  **177°** over three missing frames — inventing a flourish nobody observed.
  A visible freeze is honest; that is not.
* Gating a filter update on its *innovation against the filter's own
  prediction* (also the textbook answer) deadlocks: a held block drifts from
  the measurement, which inflates its own innovation, which keeps it held.
  That locked solo-01's entire right leg into `uncertain` for all 296
  frames. Both gates are now computed from the estimator's output alone,
  which cannot form that loop.

**7. What this hands the export stage (no export code touched).** The npz
gains a `smoothed` key: per track, `skel_states` (F, 127, 8), `visibility`,
`suppression`, `prov_observed`, `prov_interpolated`, and stats — alongside
the untouched raw `per_frame`, because a smoothed value with honest flags is
only checkable against the thing it smoothed. `export_clip_gltf`'s naive
forward-hold and leading back-fill still run unchanged; what is now
available to replace them is a per-sample answer to "is this a claim", which
is the missing input for splitting the animation into segments rather than
letting the player interpolate across a gap (`docs/PRD.md` §4's
"missing GLB keyframes do not prevent interpolation" trap).

**8. Unresolved, flagged rather than invented.**

* **`docs/OPEN-DECISIONS.md` E3 (mesh-region masking) still gates whether any
  of this is visible.** Per-joint `visibility` is now real data, but hiding a
  bone does not hide its skinned surface — until E3 is resolved the flags
  cannot be rendered, only counted. E2 (the uncertain-limb render) likewise
  stays OPEN; this module produces its input, not its answer.
* **`docs/PRD.md` §4's fourth state, `unknown`** ("where the detector simply
  cannot speak — fingers, toes"), has no representation in the frozen
  contract, whose `Visibility` enum is three-valued. Resolved here by
  inheritance (a finger answers to its wrist) rather than by adding a state;
  flagged because it is a contract gap, not an implementation choice.
* **`provenance.interpolated` is ambiguous in the schema.** "Filled in by the
  Kalman/interpolation chain across a gap rather than taken directly from a
  single frame's estimate" can be read to include every smoothed sample.
  This module sets it only where no measurement from that frame reached the
  value. Judgment call, not a decision OPEN-DECISIONS.md tracks.
* **Not measured this pass:** no Modal GPU run (the chain is CPU-only and was
  exercised against stored npz output), no GLB re-exported, nothing viewed on
  a phone. The claim "this reads less choppy" is therefore **not** made here —
  what is measured is jitter, spectrum, accent retention, and flag counts.
  Note also that with 97% of motion below 3 Hz, the most likely remaining
  cause of visible choppiness is the 15 fps sample rate itself, not noise;
  the filters carry a velocity state, so sub-sample interpolation at export
  is available if that turns out to be the real complaint.
* **Possible pre-existing bug in `services/motion-api/api.py`, not touched.**
  `_build_motion_result` treats a skel_state quaternion as "the ABSOLUTE
  local-to-parent rotation" and serves `rest⁻¹ · skel_quat` as the contract's
  local-to-parent value. The FK evidence above says skel_state rotations are
  **world** rotations (composing them as world is what makes bone offsets
  constant to CV 0.5% and round-trips to 5.7e-14 cm). If so the per-joint
  rotations currently served are wrong for every joint whose parent is not
  the identity-rotation root. `smoothing.decompose()` already produces the
  correct local-to-parent quaternion, so wiring W9 into api.py fixes it for
  free — flagged for whoever does that wiring rather than fixed here.
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
