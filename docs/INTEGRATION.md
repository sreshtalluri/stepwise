# Integration report — branch `integration`

Fourteen work packages were built in parallel on separate branches off
`rebuild-v4`, and none of them had ever been compiled, tested, or run in the
same tree. This is the record of merging them into one branch: the order, every
conflict that needed a judgement call, the full test matrix, the real end-to-end
run, and — the point of the exercise — **what turned out to be broken only once
the pieces met**.

Base: `origin/rebuild-v4`. Nothing from `main` was merged. No branch was
modified, deleted, or force-pushed; five other agents are still working off
`bone-constraints`, `w4-jobservice`, `w5-viewer` and `w8-worker`.

---

## 1. Merge order

Branches were cut off each other, not all off `rebuild-v4`, so merging in
dependency order is what keeps the conflicts small. Verified ancestry before
starting (`git merge-base --is-ancestor` over every pair) rather than trusting
the brief's diagram:

| # | Branch | Brings with it | Result |
|---|--------|----------------|--------|
| 1 | `motion-contract` | — | clean |
| 2 | `agent-base` | `motion-contract` | clean |
| 3 | `w5-viewer` | `agent-base` | clean |
| 4 | `w6-navigation` | `agent-base` | clean |
| 5 | `w7-marketing` | `agent-base` | **7 conflicts** (§2.1) |
| 6 | `w11-beats` | `w11-base` (= same commit as `w6-navigation`) | clean |
| 7 | `licensing-compliance` | — (cut from `rebuild-v4`) | clean |
| 8 | `w8-worker` | `w8-base` → `motion-contract` | clean |
| 9 | `w4-jobservice` | `w8-worker` | clean |
| 10 | `shape-params` | `w4-jobservice` | clean |
| 11 | `grounding` | `w4-jobservice` | `docs/GATE-REPORT.md` |
| 12 | `smoothing` | `w4-jobservice` | `docs/GATE-REPORT.md` |
| 13 | `compliance-d8` | `w4-jobservice` | clean |
| 14 | `bone-constraints` | `w4-jobservice` | clean — **and wrong** (§2.2) |
| 15 | `hands` | `bone-constraints` | `docs/GATE-REPORT.md` |
| 16 | `w10-masking` | `w10-base` → `w5-viewer` + `w8-worker` | `modal_app.py` (§2.3) |
| 17 | `research-contact-models` | `w4-jobservice` | clean |

`w11-base` and `w6-navigation` are literally the same commit (`98668d4`), so
merging `w11-beats` subsumes navigation. `w8-base` is cut from
`motion-contract`, **not** from `agent-base` — the CV line and the web line
diverge one commit earlier than the brief's tree suggests.

Every merge is a real merge commit (`--no-ff`), so `git log --merges` is the
audit trail and any single package can still be bisected out.

---

## 2. Non-trivial conflict resolutions

### 2.1 `apps/web` — W5 and W7 both created the same seven files

The biggest conflict by volume and the most mechanical, except for two things
that were not mechanical at all.

| File | Resolution |
|------|------------|
| `next.config.mjs` | W7 (`reactStrictMode: true`; W5's was empty) |
| `tsconfig.json` | W7 — a strict superset (adds `baseUrl` + `@/*` paths) |
| `package.json` | Union of deps = W5's exactly (W7's set is a strict subset). Pinned `next` to W5's exact `16.3.5` over W7's `^16.3.5`. Test script runs **both** globs: `lib/*.test.ts test/*.test.ts`. Kept W5's `assets` script. |
| `package-lock.json` | W5's (matches the union), re-resolved with `npm install` |
| `layout.tsx` | W7's metadata (it owns the front door) + W5's `viewport` export, which W7 lacked. Font URL is W7's — a superset (adds weight 900). |
| `app/page.tsx` | W7's. W5's dev index moved to **`/lessons`** — its own docstring ceded the route ("The real front door … is W7's package"); its relative import was repointed. |
| `globals.css` | Concatenated, but not naively — see below. |

**`globals.css` needed two real decisions, not a concatenation.**

*The `--ease` token means different things on the two branches.*
W5 defines `--ease: 160ms cubic-bezier(0.16, 1, 0.3, 1)` — duration included —
and writes `transition: height var(--ease)`. W7 splits it: `--ease` is the curve
alone and `--t: 160ms var(--ease)` is the pair. Taking W7's token block (which
we must — it is the superset, and carries `--dancer-1..4` / `--accent`, which
W5 has no equivalent of) silently reduces all four of W5's transitions to a
**zero-duration** transition: the viewer's stage promote/demote, chip toggles
and button states would simply snap, with no error anywhere. W5's four
`var(--ease)` transition uses were rewritten to `var(--t)`.

*Four class names collide with different meanings.* `.stage`, `.stages`, `.btn`
and `.chip` are defined by both branches in the same global stylesheet, and mean
unrelated things (W7's `.stage` is a marketing panel; W5's is the 3D canvas
container. W7's `.stages` is an `<ol>` of processing steps; W5's is a flex row
of viewer panels). Whichever loads second wins for shared properties. All W5
viewer markup lives under `<main class="lesson">`, so every W5 component rule is
now scoped to `.lesson` — mechanical, and it makes the collision structurally
impossible rather than ordering-dependent.

`app/global-error.tsx` (W5's finding that Next 16 requires it) survives from W5
and is what lets the build pass.

### 2.2 `process_clip.py` — a clean merge in the wrong order

Four branches touch this file. `grounding` in fact does not (the brief lists it;
the diff is empty), so it is three: `bone-constraints`, `hands`, `smoothing`.

`bone-constraints` and `hands` both insert their blocks after the
`"Finishing up"` progress emit. `smoothing` was cut from `w4-jobservice`, before
either existed, so its insertion point is *above* the `done:` print — and git
merged it there, cleanly, with no conflict at all.

That produces **temporal smoothing before spatial bone correction**, which is
backwards. Both branches say so in their own comments:
`skeleton_constraints` — *"Must run before any temporal smoothing"*;
`smoothing` — *"It runs LAST, after any per-frame anatomical correction."* They
agreed with each other and git still got it wrong, because neither could see the
other. `constrain_clip` mutates `per_frame` in place and `smooth_clip_result`
reads `per_frame`, so the merged order meant the exported `smoothed` track was
computed from **un-corrected** poses while `per_frame` carried the corrected
ones — two different skeletons in one npz.

Fixed by moving the smoothing block below the bone and hand stages. The pipeline
now reads, in order:

```
raw estimates -> bone-length constraint (spatial) -> hand/foot crops
              -> smoothing + suppression (temporal) -> export
```

This is the class of defect this whole exercise exists to catch: no conflict, no
test failure, no error message — just a silently wrong answer.

### 2.3 `modal_app.py` — add/add of neighbouring functions

`shape-params` appends `_character_with_shape` where `w10-masking` appends
`inspect_mhr_region_mapping`, and the two sides of `export_clip_gltf`'s import
block add `os` and `sys` respectively. Both sides kept in each case. Verified
afterwards that inside `export_clip_gltf` the two features compose in the right
order — shape is baked into the rest mesh, the GLB is written, and *then*
`split_glb_by_region` rewrites it in place — and that both images kept their new
dependencies (`filterpy` in `cv_image`, `pygltflib` + the
`/app/motion-api-tools` mount in `gltf_image`).

### 2.4 `docs/GATE-REPORT.md` (×4), `docs/OPEN-DECISIONS.md`

Every branch appends its own addendum section to the end of the gate report;
four of them collide on the same insertion point. All kept, in merge order:
W8 → shape → grounding → W9 → hands. No content was dropped or reconciled —
these are dated records of separate measurement sessions and are not supposed to
agree with each other. `OPEN-DECISIONS.md` auto-merged: `compliance-d8` edits
D8, `w10-masking` edits E3, `grounding` edits E6.

---

## 3. Things that were broken only in combination

The three findings below are the output of the exercise. None of them is
visible on any single branch; every branch involved is green on its own.

### 3.1 The contract moved and the viewer did not follow — `apps/web` crashed

**Severity: was fatal, now fixed.**

W8 moved `animation` out of the top level of `MotionResult` and into each
`PersonResult`, so a multi-dancer result can say which GLB and clip belong to
which dancer. W5 was cut from `agent-base`, which predates `w8-base`, and reads
`doc.animation`.

Result: `npm run assets` died with
`TypeError: Cannot read properties of undefined (reading 'clip_id')`, so the
viewer had no fixtures and `lib/motion.test.ts` could not run at all. The second
call site, `Stage3D.tsx:105`, would not have crashed — it has a
`?? gltf.animations[0]` fallback, so in a multi-dancer GLB it would have
silently played **the wrong dancer's clip**.

The irony is that W5 had already *found* this. Its own JSDoc on `glbUrls` reads:
*"`animation.glb_asset_id` is a single id for the whole document even though
`persons` is unbounded. See the report — that is a contract gap."* W8 closed the
gap; nobody told W5.

Fixed: both call sites read `person.animation` / `doc.persons[i].animation`, the
derived two-dancer fixture gives its second dancer its own `glb_asset_id`, and
the stale comment now records that the gap is closed.

### 3.2 A documented seam that neither side could connect

**Severity: silent loss of a confidence signal, now fixed.**

`smoothing.py` takes an optional `correction_m` — how far the upstream
bone-length constraint had to move each joint — and turns an over-large
correction into `low_confidence`, on the reasoning that a joint the constraint
had to yank was not usable as observed. Its docstring says *"If that module
emits a per-joint/per-frame correction magnitude, pass it as `correction_m`."*

`skeleton_constraints.constrain_clip` is that module, and it computes exactly
that displacement — then overwrites `pred_joint_coords` in place, destroying it.
`smooth_clip_result` never passed the argument. Both branches documented the
handshake from their own side and it existed on neither.

Fixed: `constrain_clip` records `bone_length_correction_m` per person (the only
moment the before/after difference exists), `smooth_clip_result` reads it and
passes it through, and stays `None` when the bone stage did not run — the
"optional by design" property is preserved. Covered by a new cross-module test
(`test_bone_constraint_correction_reaches_the_suppression_stage`) which was
confirmed to fail when the wiring is cut.

### 3.3 W9's per-joint visibility is computed, stored, and never read

**Severity: real. NOT fixed — needs a product decision, see below.**

This is the biggest finding and the only one left open.

`api.py::_build_motion_result` builds every `MotionResult` from
`data["per_frame"]` — the raw estimates — and assigns one visibility to the
whole body per frame, with this comment:

> *ponytail: every joint in a reconstructed frame gets the SAME
> observed/uncertain state … Real per-joint visibility (which limb is actually
> occluded this frame) is Milestone A's Kalman/suppression chain (W9), not built
> here.*

W9 **is** built. It is in this tree, it runs on every clip, and it writes
`smoothed[track_id]` into the npz with exactly the four arrays the contract
wants — `visibility`, `suppression`, `prov_observed`, `prov_interpolated`, per
joint per sample. `api.py` never opens that key. W9's own note anticipated it:
*"the export stage keeps reading [per_frame] until it is switched over."* The
switch-over is the thing nobody owned: W4 wrote the consumer before W9 existed,
and W9 deliberately made itself additive so as not to break W4.

So today every shipped `MotionResult` reports whole-body uniform visibility, the
viewer's per-region masking (W10's 18 `region_*` meshes, W5's
`mesh.visible` toggling) has nothing per-joint to drive it, and the real answer
is sitting unread in the same file.

**Measured on the real solo-01 run** (§5), by feeding the merged `api.py` the
merged pipeline's actual npz:

| | observed | uncertain | absent |
|---|---|---|---|
| What the shipped `MotionResult` says | 36,957 | 508 | 127 |
| What W9 computed, in the same file | 27,178 | 9,388 | 1,026 |

And the shape of it, which is the part that matters:

- `MotionResult`: **296 of 296 frames carry exactly one distinct visibility
  value across all 127 joints.** Every frame is all-observed or all-uncertain.
- W9's `smoothed`: **203 of 296 frames carry more than one.**

So the pipeline works out per-joint occlusion for 203 frames and throws it away
in all 203.

Not wired here deliberately. It is a two-line lookup, but it changes what every
lesson renders — occluded limbs would start disappearing — and that is a
product-visible behaviour change that should be made and validated by the people
who own the suppression thresholds, not slipped into an integration merge. The
hookup point is `api.py:241`: read `data["smoothed"].item()` alongside
`data["per_frame"]` and take the per-joint arrays from it when the track is
present.

### 3.4 Two finished packages that nothing imports

**Severity: architectural gap, not a defect. Not fixed — nobody owns the seam.**

`packages/navigation` (W6, 17 passing tests, ~4,000 lines) and
`packages/beat-detect` (W11, 2 passing tests) are both complete, both tested, and
**referenced by no other package in the tree.** Grepping `apps/web` for
`@stepwise/navigation` returns only `next/navigation`. Grepping the service for
`beat_detect` returns nothing.

The chain that would connect them does not exist at any link:

- `beat_detect.propose_grid()` takes a video path and returns a beat grid. No
  Modal function calls it, and `run_clip` never touches audio.
- `MotionResult` has **no beats or counts field at all** — grep the schema for
  `beat` or `count` and there are zero hits. So even if the grid were computed,
  the frozen contract has nowhere to put it.
- `<LessonNavigator>` is fully controlled and wants that structure from its host.
  `LessonViewer.tsx` (W5) instead grew its own transport, chips and scrub bar
  inline.

So the count strip, parts and loops — PRD §5's authoring surface — exist twice
in spirit and zero times in the running product. This is not something an
integration merge can decide: it needs a contract change (a new `beats`/`counts`
block in `MotionResult` v1.1, or a separate document), which is exactly the kind
of decision `docs/OPEN-DECISIONS.md` exists for and which is not recorded there.
Flagged, not invented.

### 3.5 Smaller notes

- **`evaluation/clips.yaml`** merged cleanly. `w8-worker` repurposed
  `violator-duet` (a duet is no longer a violation under the revised 6-dancer
  MVP) and `hands` added its own entry; the two edits do not overlap.
- **W8 ships a real `two-dancer-lesson.json` fixture** and W5's asset script
  *derives* its own two-dancer document from `good-lesson.json`. Both are valid
  against the schema and both are kept — W5's derived one also exercises a
  crossing, which the shipped fixture does not. Worth collapsing later; not an
  error.
- **Known issue carried forward, not introduced here:**
  `api.py::_build_motion_result` treats `skel_state` quaternions as
  local-to-parent when they are world transforms. Pre-existing on
  `w4-jobservice`; out of scope for this merge and left untouched.

---

## 4. Test matrix

Every suite in the tree, run on the merged branch.

| Suite | Tests | Result |
|-------|-------|--------|
| `packages/motion-contract` — TypeScript (`test/ts/validate.test.ts`) | 14 | **14 pass** |
| `packages/motion-contract/python` (`tests/test_validate.py`) | 14 | **14 pass** |
| `packages/navigation` (`test/core.test.ts`) | 17 | **17 pass** |
| `packages/beat-detect/python` (`tests/test_propose.py`) | 2 | **2 pass** |
| `apps/web` — W7 `test/*.test.ts` + W5 `lib/motion.test.ts` | 20 | **20 pass** (after §3.1) |
| `tools/test_skeleton_constraints.py` | 12 | **12 pass** |
| `tools/test_hand_crops.py` | 8 | **8 pass** |
| `tools/test_smoothing.py` | 8 + 1 new | **9 pass** |
| `tools/test_process_clip.py` | 5 | **5 pass** |
| `tools/test_rtmo_detector.py` | 7 | **7 pass** |
| `services/motion-api/test_grounding.py` | 15 | **15 pass** |
| `services/motion-api/tools/test_region_mask.py` | 8 | **8 pass** |
| **Total** | **131** | **131 pass, 0 fail** |

One failure was seen and it was real, not flaky: `lib/motion.test.ts` (§3.1).
No test was loosened, skipped, or deleted to make this table green. One test was
added — the cross-module check for §3.2.

**Reproducing the Python suites.** They import as flat modules, so
`PYTHONPATH=.:tools` from `services/motion-api/vendor/fast-sam-3d-body`. Beyond
`numpy`/`scipy`/`pytest` they need `filterpy` (smoothing), `pygltflib` +
`opencv-python-headless` (region mask, hand crops) and `onnxruntime` + `rtmlib`
(rtmo detector).

**`apps/web`**: `npm run build` and `tsc --noEmit` both clean. `npm run assets`
must run first — the viewer tests read `public/fixtures/`. Routes built: `/`,
`/upload`, `/job/[jobId]` (W7) and `/lessons`, `/lesson/[lesson]` ×3 (W5).

---

## 5. End-to-end on Modal

`modal run modal_app.py::run_clip --clip-id solo-01` on the merged branch, which
dispatches `export_clip_gltf` itself (W4). Real GPU session, real clip, real
GLB. Job `job_solo-01_1789952505`.

**It completed.** Final job-status document:

```json
{"schema_version": "1.0.0", "job_id": "job_solo-01_1789952505",
 "state": "succeeded", "stage_message": "", "progress": 1.0,
 "error": null, "retry_count": 0}
```

### The merged pipeline, in the order it actually ran

```
done: 291/296 frames reconstructed, 146.5s total (2.02 fps), peak VRAM 3.69 GB
  bone lengths, track 1: 117 bones fixed, worst frame off by 2.36x,
                         192/291 frames carry an uncertain joint
  crops, track 1: hands 289/291 frames, feet 278/291 frames
  smoothing track 1: 27178 observed, 9388 uncertain, 1026 absent joint-samples
                     (17 physically impossible)
SAVED /results/solo-01.npz
track 1: 291/296 samples observed (first at 1, leading gap back-filled)
track 1: shape from 291 frames, ||shape||=2.845, per-frame std mean=0.199;
         rest-mesh displacement mean=0.2491 cm max=2.1354 cm
SAVED /results/solo-01_track1.glb (single mesh, pre-region-split)
SAVED /results/solo-01_track1.glb (region-split)
```

Bone constraint, then hand crops, then smoothing — §2.2's fix, confirmed on real
hardware rather than by reading the diff. `27178 + 9388 + 1026 = 37592 = 296 × 127`,
so every joint-sample is accounted for.

### Cost and runtime

| | |
|---|---|
| GPU | L40S (`GPU_TIER` default) |
| Clip | `solo-01`, 19.7 s, 576×1024, sampled at 15 fps → 296 frames |
| Reconstruction wall time | **146.5 s** (2.02 fps) |
| Peak VRAM | **3.69 GB** |
| **Cost, reconstruction** | **$0.1279** (`solo-01.performance.json`) |
| Image build, this pass | ~13 min, one-off — `filterpy` (W9) and `pygltflib` (W10) landed in already-built layers and invalidated the cache below them, including the Detectron2 compile |

2.02 fps against the 3.79 fps in `docs/GATE-REPORT.md`'s W1 measurement. Not
investigated: the gate figure predates the bone, hand-crop and smoothing stages
and this was a cold container on a freshly rebuilt image. Recorded as measured,
not explained.

### Verification of the exported GLB

Measured directly on the downloaded `solo-01_track1.glb` (1.94 MB), not inferred
from logs.

| Check | Result |
|-------|--------|
| GLB produced | yes, 1,936,912 bytes, one animation, 218 channels |
| **Non-finite animation values** | **0 / 222,296** |
| **Non-finite mesh vertices** | **0 / 30,498 components** (10,166 verts) |
| **Region meshes** | **18 / 18 present and named `region_*`**, every one with a non-zero triangle count |
| **Shape bake applied** | yes — shape fitted from all 291 observed frames, `‖shape‖ = 2.845`, rest-mesh displacement 0.2491 cm mean / 2.1354 cm max |
| Bone-length stability | see below — **not** the flat 0.0000% the brief expects |

The finite-check guard (the one that exists because a past bug wrote NaN into
frame 0 and made the whole model invisible) survived the merge and is still on
the path: it is inside `export_clip_gltf` and runs before every write.

Region triangle counts, for the record:
`torso_lower 766, torso_upper 154, neck 85, head 2152, collar_l 125, collar_r
124, upperarm_l 204, upperarm_r 204, forearm_l 370, forearm_r 370, hand_l 1764,
hand_r 1764, thigh_l 228, thigh_r 228, shin_l 334, shin_r 334, foot_l 294,
foot_r 294`. W10's `RegionMappingError` path did not fire — the tolerant matcher
resolved all 18 canonical bones against the real `lod3.fbx` skeleton, which the
W10 report had flagged as its single biggest unverified assumption. **That
assumption is now verified on real hardware.**

### The HTTP layer, against real merged output

The last seam worth checking is whether `api.py` — W4's layer, written before
half of the branches below it existed — can still turn this npz into a document.
Fed the real `solo-01.npz` and the real export manifest, with only the two Modal
volume reads stubbed:

```
MotionResult VALIDATES against the frozen v1 schema
persons=1  samples=296  joints=127
person.animation = {'clip_id': 'solo-01_track1', 'glb_asset_id': 'solo-01_track1.glb'}
grounding.status = none
shape_params.source = well_observed_frames
crop_rects: 289/296 frames have a hand rect
```

One call exercises five packages at once and they agree: W8's per-person
`animation` block is populated, `shape-params` reports
`source = well_observed_frames` rather than `default_assumed` (so the bake is
being credited honestly), `hands` supplies 289 crop rects, and `grounding` runs
a real floor solve. That solve returns `none` —
`reason: contacts_not_spread_over_clip`, contacts covering 6 s of a 20 s clip
against a 0.6 threshold, with inlier RMS 0.01338 m and tilt 3.078°. That is the
documented E6 behaviour, not a merge failure: the floor is found and then
honestly refused for want of temporal coverage.

### Bone lengths are not flat, and it is not the merge's fault

Expected CV 0.0000%. Measured across all 119 real bones in the GLB:

```
CV: mean = 2.1426%   median = 0.0002%   max = 73.7855%
bones with CV < 0.01%: 72 / 119
```

The median is essentially zero and the major limbs are *exactly* zero
(`l_lowleg`, `r_lowleg`, `r_foot`, the upleg twists: 0.0000%). The constraint
works. The mean is dragged up by two groups:

1. **Three sub-3 mm procedural joints** — `c_neck_twist0_proc` (2.58 mm mean),
   `l_talocrural` / `r_talocrural` (1.69 mm). At that scale a relative CV is
   not a meaningful number.
2. **Every finger bone below both wrists**, all at an *identical* 1.2855% —
   identical because it is one uniform rescale, not per-bone noise. The cause
   is visible in the GLB: `r_wrist` and `l_wrist` are the only two nodes in the
   file carrying an animated **`scale`** channel, varying 0.8925 → 0.9643 over
   the clip.

`skel_state` is `(J, 8)` = 3 translation + 4 quaternion + **1 scale**.
`constrain_clip` rewrites `skel_state[:, :3]` only — deliberately, and its
docstring gives the reason: *"the node translation channels carry the full 24.4%
CV, so this is the channel that reaches the viewer."* That was true when it was
measured. Index 7 is a second channel that also reaches the viewer, and a
time-varying scale on a wrist rescales its entire hand subtree.

**Checked against a control.** `solo-01-bonefix_track4.glb` — the
`bone-constraints` branch's own verification export, made before any of this
merge — measures mean 2.1426%, median 0.0002%, max 73.7808%, 72/119 under
0.01%. Identical. **This is pre-existing behaviour, not an integration
regression**, and it is reported here because the brief's "CV 0.0000%" is a
claim about the limbs, not about the skeleton. Left unfixed: constraining the
scale channel is the bone-constraint module's decision, and that branch has an
agent on it.

---

### Verdict

The merged pipeline runs end to end on real hardware and produces a valid,
renderable, finite GLB with all four features (shape bake, bone constraint, hand
crops, region split) present and composing in the right order. One real ordering
defect was found and fixed before this run; one signal was reconnected; one
computed-and-discarded output and one pre-existing bone-scale gap are reported
and left to their owners.

---

## 6. Ground rules honoured

- Work only on `integration`, cut from `origin/rebuild-v4`. Pushed.
- `main` never merged. No force-push. No other branch touched, renamed, or
  deleted.
- `docs/DESIGN.md`, `CLAUDE.md` and `docs/OPEN-DECISIONS.md` carry only the
  edits the merged branches already made to them; this integration pass added
  no new decisions to them of its own.

---
---

# Second integration pass — branch `integration-2`

Four more branches landed after the first pass merged fourteen. Same exercise,
same question: **what is broken only once the pieces meet?** This pass found
one defect of exactly that kind, and it is the worst sort — a clean merge, no
conflict, no failing test, silently reverting four packages at once (§9.1).

Base: `origin/integration`. Nothing from `main` merged. No branch modified,
deleted or force-pushed. Everything below is measured on the merged branch,
including a real Modal L40S session.

---

## 7. Merge order

All four branches are independent of each other — each was cut from something
already inside `integration` (`bone-constraints`, `w4-jobservice`,
`w5-viewer`). Ancestry was verified with `git merge-base --is-ancestor` before
starting; none of the four was already an ancestor of `integration`.

| # | Branch | Cut from | Result |
|---|--------|----------|--------|
| 1 | `export-quality`    | `bone-constraints` | 3 conflicts (§8.1, §8.2) |
| 2 | `world-placement`   | `bone-constraints` | 2 doc conflicts (§8.3); **`api.py` auto-merged** |
| 3 | `camera-follow`     | `w5-viewer`        | clean (§8.4) |
| 4 | `caching-retention` | `w4-jobservice`    | 5 conflicts, one of them the whole point of this pass (§9.1) |

Order is deliberate. `caching-retention` moves `_build_motion_result` out of
`api.py` into a new `motion_result.py`, so it had to go **last**: whatever the
other three had done to that function needed to be in the tree before it was
picked up and carried. As §9.1 explains, going last was necessary but nowhere
near sufficient — git moved the file without any of their work in it.

Every merge is a real merge commit (`--no-ff`).

---

## 8. Conflict resolutions

### 8.1 `modal_app.py` — two post-export GLB passes, and the order matters

`export-quality` adds `_rewrite_interpolation_linear` (pymomentum always emits
`STEP`; there is no knob, so the sampler mode is patched after the fact).
`w10-masking` had already added `split_glb_by_region`. Both rewrite the same
GLB with pygltflib, and the merge had to decide which runs first.

**Region split first, interpolation rewrite last.** The split leaves animation
samplers untouched but *does* rebuild the binary chunk (it appends accessors
for the 18 sub-meshes). So either order leaves `LINEAR` in the file — but only
this order leaves it *verified*: `_rewrite_interpolation_linear` ends by
re-reading the file and asserting three things (its own rewrite changed no
binary bytes, every sampler is `LINEAR`, no non-finite float in the chunk), and
those assertions are worth far more against the bytes actually shipped than
against an intermediate. As a bonus the finite check now also covers the
split's new vertex accessors.

There is a real failure mode hiding in this choice: the rewrite's "my rewrite
must not change the binary chunk" guard runs on a file pygltflib has just
written, so if a load/save round-trip were not byte-stable on a split output,
**every export would raise instead of shipping**. That is not obvious from
reading either branch, so it is now covered by a test rather than by hope:
`tools/test_region_mask.py::test_region_split_then_interpolation_rewrite_compose`
builds a synthetic skinned GLB with STEP animation, runs both stages in the
merged order, and asserts the composition. Confirmed independently by the real
run: `218/218 samplers rewritten to LINEAR` (§10).

`gltf_image` also needed the union of three branches' additions — W10's
`add_local_dir`, `export-quality`'s `pygltflib`, and `caching-retention`'s two
mounts — plus `grounding.py`, for the reason in §9.1.

### 8.2 `OPEN-DECISIONS.md` — an id collision, not a text conflict

`export-quality` appended two new rows numbered **E6** and **E7**. `E6` was
already taken: `grounding` had used it for world placement, and
`world-placement` was about to rewrite that same row. Two different decisions
would have shipped under one id, and the losing one would simply have vanished
on the next edit.

Renumbered `export-quality`'s pair to **E7** (reconstruction frame rate) and
**E8** (bone direction in the glTF translation channel), leaving **E6** to
world placement. `GATE-REPORT.md`'s two citations were updated in the same
commit, so the prose and the table still agree.

Worth noting for the next parallel batch: nothing prevents this. Branches pick
the next free id against *their own* base, and two branches cut from the same
commit will always pick the same one.

### 8.3 `api.py` auto-merged where two branches edited adjacent lines

`export-quality` rewrites the per-joint rotation loop; `world-placement`
rewrites the `root_trajectory` comment immediately below it. Git merged both
without a conflict. Checked by hand rather than trusted — the result is
correct, both survive, and the composition reads properly: the per-joint
rotations are now parent-relative, and the root's rotation carries a new note
explaining why it is deliberately *not* converted (the root has no parent, so
its world rotation already is its local one).

`GATE-REPORT.md` and `DESIGN.md` collided only as appends; all content kept, in
date order. In `DESIGN.md` one line was not an append (§9.2).

### 8.4 `camera-follow` — clean, but verified against the first pass's fixes

This branch was cut from `w5-viewer` and therefore predates all three of the
first pass's `apps/web` fixes, so a clean merge is exactly when to look. Both
risks came back negative:

* every `animation` read is still per-person (`doc.persons[i].animation`), so
  W8's contract move is not undone — the §3.1 regression did not return;
* `globals.css` is untouched by this branch, and no `var(--ease)` is used as a
  duration+curve shorthand — the §2.1 zero-duration trap is not re-armed.

---

## 9. What was broken only in combination

### 9.1 A "verbatim lift" that silently reverted four packages

**Severity: would have shipped a visibly wrong skeleton. Found and fixed.**

This is the finding this whole exercise exists to catch, and it is a cleaner
specimen than the first pass's §2.2.

`caching-retention` moves the `MotionResult` assembly out of `api.py` into a
new `services/motion-api/motion_result.py`, so the GPU worker can build the
document once at export time and the 61 MB npz can then be deleted. The
module's own docstring says it was *"lifted verbatim out of api.py (W4)"*.

That is true — of `api.py` **as it stood on `w4-jobservice`**, which is where
the branch was cut. By the time the move landed, four other packages had
already changed the exact function being moved:

| Package | What `api.py` had gained | What the w4-era copy has instead |
|---|---|---|
| `export-quality` | `_local_rotations` — the world-vs-local rotation fix | raw `skel_state` quaternions, i.e. **the bug**, a measured median of **125.7°** wrong per joint below the root |
| `grounding` | the real floor solve | hardcoded `{"status": "none", "floor_plane": None}` |
| `grounding` | `camera_intrinsics_from_clip` | the `fx=fy=max(w,h)` placeholder, **12.8% low** on solo-01 |
| `hands` | per-frame hand/foot crop rects | `[None] * n_samples` |
| `world-placement` | the corrected `root_trajectory` rationale | the diagnosis that branch had just overturned |

**Git produced no conflict for any of it.** The new file is an add; `api.py`'s
copy of those functions is a clean delete. There is no textual overlap to
conflict on, and both halves merge perfectly. Nor does any test catch it: the
assembly has no unit test, and `test_api_rotations.py` — the one suite that
would have noticed — imports from `api`, so it would have failed with
`ImportError` on a missing symbol rather than an assertion about rotations.
An `ImportError` reads like a trivial path problem and invites exactly the
wrong fix.

Had this merged as git offered it, the pipeline would have kept exporting a
correct GLB while **serving a MotionResult describing a different skeleton** —
the two artefacts of the same clip disagreeing, with nothing failing anywhere.

Resolved by rebuilding `motion_result.py` from the **merged** builder rather
than taking either side, then re-applying the two things the move actually
intended:

1. the pure signature (all inputs passed in) and `MotionResultUnavailable` in
   place of fastapi's `HTTPException`, so the module imports in a container
   with no web framework;
2. `shape_params.vector` no longer leaving the server.

`grounding.py` is now mounted into `gltf_image` alongside it — pure numpy, no
torch, so it costs that image nothing. Verified on the real run: the
`[grounding]` diagnostics print from the **export** stage, which is the merged
assembly running on the GPU worker.

`test_api_rotations.py`'s import follows the functions to their new home. Same
six tests, same assertions, nothing relaxed.

**The general lesson, since this will recur:** "moved verbatim" is a claim
about a file at a point in time, and a long-lived branch cannot make it about
the file today. A move is the one refactor git cannot help with — it destroys
the textual adjacency conflicts are made of. Any branch that relocates a
function that other branches are editing needs the move re-derived at merge
time, not replayed.

### 9.2 `DESIGN.md` would have silently restored a retired constraint

**Severity: product copy regression. Caught in the conflict.**

`caching-retention` rewrites the landing-page copy block to add the takedown
and retention lines. Its version of the neighbouring "Works best with" line
still says **"one dancer"** — correct when the branch was cut, wrong since PRD
§5's 2026-09-18 multi-dancer revision, which `integration` already carries.

Taking that side wholesale would have restored a constraint the product no
longer has, in the one place a first-time visitor reads it, as a side effect of
a change about retention. Kept `integration`'s corrected line, took
`caching-retention`'s new rights and retention copy.

Same shape as §9.1: a branch faithfully carrying its own base forward over work
it never saw.

### 9.3 A test that had never run

**Severity: low, pre-existing on the branch, not a merge break. Fixed.**

`test_fingerprint.py::test_separation` passes `decimals=0` to ffmpeg's
`testsrc2` filter. `decimals` belongs to `testsrc`; `testsrc2` has no such
option, so ffmpeg rejects the whole filtergraph and the clip generator raises
`CalledProcessError`. The test could not have passed on any ffmpeg.

Confirmed pre-existing (the file is byte-identical to `origin/caching-retention`)
and reported rather than quietly absorbed. Fixed by dropping the invalid
option — not by relaxing an assertion: the test now actually runs the
separation it was written to measure, and passes. It is the suite that checks
dedupe does not fuse two different dances, so leaving it dead was not an option.

### 9.4 Open items, confirmed unchanged

Both first-pass open items were re-checked on the merged branch. **Neither is
affected by these four merges, and neither is fixed here.**

* **W9's per-joint visibility is still computed and still discarded** (§3.3).
  The assembly reads `data["per_frame"]` and never `data["smoothed"]`; grep for
  `smoothed` in `motion_result.py` returns nothing. The real run confirms both
  halves are live: the npz carries `smoothed` for track 1 with all four
  per-joint arrays (`visibility`, `suppression`, `prov_observed`,
  `prov_interpolated`) plus `skel_states`, and the served document still
  reports one visibility value for the whole body per frame. The hookup point
  simply moved with the function — it is now in `motion_result.py`, not
  `api.py:241`. Still a product decision, still unowned.
* **`packages/navigation` and `packages/beat-detect` are still imported by
  nothing** (§3.4). Grepping the whole tree for `@stepwise/navigation` and
  `beat_detect` outside their own directories returns zero hits. A separate
  agent is reportedly writing the contract; nothing in these four branches
  touches it. **Closed on branch `lesson-structure` — see §13 below.**

Also unchanged and re-measured, not re-argued: **bone-length CV is not flat**
(§5). Measured on this pass's GLB — mean 2.1504%, median 0.0002%, max 74.0992%,
72/119 bones under 0.01% — against the first pass's 2.1426 / 0.0002 / 73.7855 /
72. Same distribution, same cause: `l_wrist` and `r_wrist` are the only two
nodes carrying an animated `scale` channel, which rescales each hand subtree.
Pre-existing, `bone-constraints`' call, untouched here.

---

## 10. Test matrix

Every suite in the tree, on the merged branch. Python 3.12.

| Suite | First pass | Now | Result |
|-------|-----------|-----|--------|
| `packages/motion-contract` — TypeScript (`test/ts/validate.test.ts`) | 14 | 14 | **14 pass** |
| `packages/motion-contract/python` (`tests/test_validate.py`) | 14 | 14 | **14 pass** |
| `packages/navigation` (`test/core.test.ts`) | 17 | 17 | **17 pass** |
| `packages/beat-detect/python` (`tests/test_propose.py`) | 2 | 2 | **2 pass** |
| `apps/web` — `test/copy.test.ts` | — | 10 | **10 pass** |
| `apps/web` — `test/logic.test.ts` | — | 4 | **4 pass** |
| `apps/web` — `lib/motion.test.ts` (grew on `camera-follow`) | 6 | **13** | **13 pass** |
| `services/motion-api/test_api_rotations.py` (new, `export-quality`) | — | **6** | **6 pass** |
| `services/motion-api/test_fingerprint.py` (new, `caching-retention`) | — | **2** | **2 pass** (§9.3) |
| `services/motion-api/test_retention.py` (new, `caching-retention`) | — | **10** | **10 pass** |
| `services/motion-api/test_grounding.py` | 15 | 15 | **15 pass** |
| `services/motion-api/tools/test_region_mask.py` | 8 | **9** | **9 pass** (+1, §8.1) |
| `tools/test_skeleton_constraints.py` | 12 | 12 | **12 pass** |
| `tools/test_hand_crops.py` | 8 | 8 | **8 pass** |
| `tools/test_smoothing.py` | 9 | 9 | **9 pass** |
| `tools/test_process_clip.py` | 5 | 5 | **5 pass** |
| `tools/test_rtmo_detector.py` | 7 | 7 | **7 pass** |
| **Total** | **131** | **157** | **157 pass, 0 fail** |

131 → 157 is +26: 18 from the three new suites, +7 on `lib/motion.test.ts`
(`camera-follow`), +1 added here for the two-stage GLB rewrite (§8.1).

**No test was loosened, skipped or deleted.** Two were changed, neither in a way
that weakens it: `test_api_rotations.py`'s import follows the functions it tests
to their new module (§9.1), and `test_fingerprint.py`'s ffmpeg invocation was
corrected so the test runs at all (§9.3).

**`apps/web`**: `npm run build` and `tsc --noEmit` both clean. `npm run assets`
must run first. Routes built: `/`, `/upload`, `/job/[jobId]`, `/lessons`,
`/lesson/[lesson]` ×6.

**Reproducing the Python suites.** Unchanged from §4, plus `python-multipart`
(`test_retention.py` posts multipart uploads through fastapi), `soundfile` for
beat-detect, and the `ffmpeg`/`ffprobe` **binaries** on PATH for
`test_fingerprint.py` — a subprocess dependency, not a Python one.

---

## 11. End-to-end on Modal

`modal run modal_app.py::run_clip --clip-id solo-01` on the merged branch. Real
L40S session, real clip, real GLB. App `ap-gKY9QRC5YLYqygoy0tzE2s`, final
job-status `succeeded`, progress `1.0`.

### Measured cost and runtime

| | This pass | First pass |
|---|---|---|
| Reconstruction | **87.1 s (3.40 fps)**, 291/296 frames | 146.5 s (2.02 fps) |
| Wall clock incl. export | **140.9 s** | — |
| Peak VRAM | **3.69 GB** | 3.69 GB |
| **Cost** | **$0.0763** | $0.1279 |
| Image build | none — mounts only | ~13 min |

3.40 fps against the first pass's 2.02 and `GATE-REPORT.md`'s 3.79. The first
pass's own note applies: that run was a cold container on a freshly rebuilt
image. This pass changed only mounted files, so nothing rebuilt. Recorded as
measured, not explained.

### The merged pipeline, in the order it actually ran

```
done: 291/296 frames reconstructed, 87.1s total (3.40 fps), peak VRAM 3.69 GB
  bone lengths, track 1: 117 bones fixed, worst frame off by 2.36x,
                         177/291 frames carry an uncertain joint
  crops, track 1: hands 289/291 frames, feet 278/291 frames
  smoothing track 1: 27367 observed, 9200 uncertain, 1025 absent (17 impossible)
SAVED /results/solo-01.npz
sample rate from npz timeline: 15.0 fps (296 samples)      <- derived, not hardcoded
track 1: shape from 291 frames, ||shape||=2.846, rest-mesh mean=0.2492 max=2.1354 cm
SAVED solo-01_track1.glb (single mesh, pre-region-split)
track 1: region triangle counts: {18 regions, all non-zero}
SAVED solo-01_track1.glb (region-split)
SAVED solo-01_track1.glb (region-split, 218/218 samplers rewritten to LINEAR)
[grounding] solo-01: none -- contacts_not_spread_over_clip
[job-status] succeeded 1.0
```

The `§2.2` stage order survives (spatial → crops → temporal), and the two new
post-export stages compose in the §8.1 order. The `[grounding]` line printing
here — from the *export* stage, not the API — is the merged assembly running on
the GPU worker with `grounding.py` mounted (§9.1).

### Verification of the exported GLB

Measured directly on the downloaded file, not read from the log.
Reproduce: `python services/motion-api/verify_glb.py <file.glb> --expect-fps 15.0`.

| Check | Result |
|---|---|
| GLB produced | yes, **1,937,632 bytes**, 1 animation, 218 channels |
| **Interpolation** | **LINEAR on 218/218 samplers. Zero STEP.** |
| **Keyframe rate** | **15.0 fps** (dt = 0.066667 s) — matches the npz's real derived rate |
| **Non-finite animation values** | **0 / 222,296** |
| **Non-finite mesh vertices** | **0 / 30,498 components** |
| **Region meshes** | **18 / 18 present and named `region_*`, none empty** |
| **Shape bake applied** | yes — fitted over all 291 observed frames, `‖shape‖ = 2.846`, rest-mesh displacement 0.2492 cm mean / 2.1354 cm max |
| Bone-length CV | mean 2.1504%, median 0.0002%, max 74.0992%, 72/119 under 0.01% — unchanged from §5, pre-existing |

### Verification of the MotionResult

The document the GPU worker materialised and stored — i.e. the one a client
actually receives, not a reconstruction of it.

```
MotionResult VALIDATES against the frozen v1 schema
  persons=1  samples=296  joints=127
  person.animation      = {'clip_id': 'solo-01_track1', 'glb_asset_id': 'solo-01_track1.glb'}
  shape_params          = {'source': 'well_observed_frames'}   ('vector' absent)
  crop_rects            = hands 289/296, feet 278/296
  camera.intrinsics.fx  = 1174.88        (the placeholder would be 1024.0)
  grounding.status      = none           (contacts_not_spread_over_clip)
  non-finite numbers anywhere in the document: 0
```

Every line above is a package that §9.1 would have silently dropped, still
present: real intrinsics and a real (honestly refused) floor solve from
`grounding`, real crop rects from `hands`, the shape source from `shape-params`
with its vector correctly withheld by `caching-retention`, and the per-person
animation block from W8.

**The per-joint rotations are the fixed, world-derived ones.** Not inferred —
both hypotheses were recomputed from the npz and compared against what the
document actually serves, over 40 frames × 127 joints:

```
served vs world-derived (fixed) : max per-component difference 0.000e+00
served vs raw skel_state quats  : median 137.5 deg, max 180.0 deg
```

Exactly the fixed values, and nowhere near the buggy ones. This is the check
that would have failed had §9.1 merged as git offered it.

### npz slimming did not break the export

`caching-retention` drops `pred_vertices` and `expr_params` before saving.
Confirmed on the merged code, three ways:

1. **On the real run.** `solo-01.npz` is **4,416,302 bytes**, down from the
   61.30 MB the first pass measured — a 92.8% reduction. `pred_vertices` and
   `expr_params` are absent; `skel_state`, `shape_params`, the crop rects and
   W9's `smoothed` block (all four per-joint arrays plus `skel_states`) are all
   still there.
2. **Byte-identical documents.** Rebuilding the `MotionResult` from that
   slimmed npz via `api.py`'s fallback path produces **7,153,078 characters,
   byte-identical** to the 7,153,078 the GPU worker materialised. The two paths
   agree exactly.
3. **The invariant, not just this clip.**
   `services/motion-api/check_npz_slimming.py` builds a fat npz and its
   stripped twin and asserts the documents are identical and `skel_state` is
   untouched. Worth having: the merged assembly reads *more* of the npz than
   `caching-retention`'s copy did (the floor solve reads `raw_detections`), so
   "the slimming is safe" needed re-checking against the merged reader, not the
   branch's.

### Verdict

All four branches compose. The exported GLB is finite, LINEAR-interpolated at
the clip's real 15.0 fps, carries all 18 non-empty region meshes and the baked
shape; the served MotionResult validates against the frozen contract and
carries the corrected rotations. One silent four-package reversion was caught
and undone, one copy regression caught, one never-executed test made to run.
Both known open items are confirmed unchanged and still unowned.

---

## 12. Ground rules honoured

- Work only on `integration-2`, cut from `origin/integration`. Pushed.
- `main` never merged. No force-push. No branch modified, renamed or deleted —
  `export-quality`, `caching-retention`, `camera-follow` and `world-placement`
  are untouched at the commits they were read from.
- `docs/DESIGN.md` and `docs/OPEN-DECISIONS.md` carry only the edits the merged
  branches made to them, plus the E6/E7/E8 renumbering §8.2 forced. This pass
  opened no decisions of its own and closed none.

---
---

# Closing §3.4 — branch `lesson-structure`

Two finished, tested packages that nothing imported, and a contract with
nowhere to put what one of them produced. That gap blocked the MVP's core
promise — learning a dance **by counts** — so this branch closes it end to end:
a beat proposal is computed on every job, carried in the contract, and rendered
by W6's count strip against a real `MotionResult`.

Base: `origin/integration-2`. Nothing from `main` merged. No other branch
touched. `docs/DESIGN.md` is unchanged — this branch opened no design decisions
of its own.

---

## 13. Where the beat proposal lives, and why

**In `MotionResult`, as an optional top-level `proposed_counts` block.** Not in
a second document, not on a second endpoint.

The decision rests on the distinction the surface has to make anyway, which is
between **two different kinds of count grid**:

| | machine | human |
|---|---|---|
| what | `MotionResult.proposed_counts` | `LessonStructure` (W6's `{grid, parts}`) |
| produced by | `beat_detect.propose_grid()` on the clip's audio | the learner, by hand |
| scope | one per job | one per learner per lesson |
| lifetime | immutable | edited constantly |
| lives in | the contract | client storage today, a server store once D5 lands |

The proposal is a per-clip, server-computed, immutable fact, produced by the
same job from the same source file and wanted by the same consumer at the same
moment as everything else in the document. It is in-family: the contract
already carries `accent_color` (sampled from pixels) and
`source_video.audio_offset_s` (which exists precisely so a video time can be
mapped to an audio one), so "a fact about this clip that the viewer needs" is
what this document already is.

The alternatives were each worse in the same specific way. A separate stored
artifact or endpoint would need its own serving path, its own versioning, and
its own line in the deletion list that `OPEN-DECISIONS.md` **D7** promises —
and that promise is kept by a literal list of filenames in
`retention.clip_artifact_paths`. The cheapest way to break a deletion promise
is to add a file to the system and forget to add it to that list. One field on
a document that is already stored, served and deleted adds no such surface.
(The pipeline *does* write one intermediate `{clip_id}.beats.json` for the
hand-off between stages; it is in the list, and `test_retention.py`'s
"survivors == [tombstone]" assertion now covers it, so it cannot be forgotten
quietly.)

**Authored structure deliberately does NOT go here and cannot.** `MotionResult`
is the frozen output of a finished job and every consumer holds the same copy;
authored counts are per-learner and mutable. Putting them in the same document
would mean either a mutable `MotionResult` or one document per learner, and
both are worse than the storage question they would be trying to avoid.

### What travels with the grid

All of it: `confidence`, `bpm`, `alternates` (the half- and double-time
readings), and `warnings`. Stripping a `ProposedGrid` down to
`{countOneS, secondsPerCount, countTotal}` is exactly the operation that turns
W11's honest guess into an unmarked fact, and `.to_grid()` — which does that
stripping — is for the last step into the UI, not for the wire.

The half/double alternates matter more than they look. librosa's tracker
locking onto 2x or 0.5x a human's tempo is not an exotic failure, it is the
single most likely way the proposal is wrong, and carrying both readings means
the correction is one tap rather than re-tapping the whole dance.

### The honest limitation, stated where it is read

`beat_track` finds **beats, not downbeats**. It has no notion of which beat
begins an eight, so `count_one_s` is the first beat in the clip and is usually
*not* count 1 of the dance. Measured on a synthetic 10 s 128 BPM click track
(the first click at t = 0.000): spacing came back 0.9% high (129.2 a minute),
confidence 0.96, and `count_one_s` came back **0.488 s** — not the first click.
The strong number and the weak number in the same result.

So the schema says it, the navigation copy says it, and the viewer says it
above the count strip. One line of copy had to be *repaired* for this:
`packages/navigation/src/copy.ts` read *"Set these by hand. Nothing here was
detected from the music"*, which was true when beat detection was a cut-list
item and became **false** the moment a proposal could reach the surface. That
is a §7h failure of exactly the documented shape — a sentence written as an
accurate statement of the world, left behind by the world.

---

## 14. The versioning rule, written down instead of inferred

`schema_version` stays **`1.0.0`**.

The rule is now in `motion-result.schema.json` and
`packages/motion-contract/README.md` rather than in someone's head:

- **Bump** when an existing valid document becomes invalid, or an existing
  correct consumer becomes wrong: a field removed or renamed, a meaning
  changed, a new *required* field, an enum value removed, a type narrowed.
- **Do not bump** for an additive-optional field or a relaxation
  (required → optional, enum widened).
- Consumers detect an optional field **by checking for the field**, never by
  comparing versions.

The reason not to bump is not laziness, it is the field's own contract: the
schema tells consumers to *refuse* an unrecognized version rather than guess,
so a gratuitous bump makes every deployed consumer reject documents it could
read perfectly well.

This documents what already happened rather than inventing a policy.
`caching-retention` relaxed `shape_params.vector` from required to optional and
correctly kept `1.0.0`; that decision was right and unrecorded, and this branch
had to reverse-engineer it. Both changes now sit under one stated rule.

One new cross-field invariant, in both validators: `count_total` must equal the
grid laid over `sample_times_s`, the same formula `normalizeStructure` uses.
The realistic way to get it wrong is to size the grid against
`source_video.duration_s` — off by exactly one count, and silent everywhere
else. `services/motion-api/test_proposed_counts.py` asserts the service's
number and the contract's validator agree, and that the invariant actually
fails when the number is wrong.

---

## 15. Beat detection does not go in `cv_image`

**It gets its own image, and that is measured rather than cautious.**

`librosa` pulls `numba`, and `numba` pins `numpy` hard. `cv_image`'s numpy is
load-bearing in three directions at once:

1. Detectron2 compiles a CUDA extension against it;
2. bytetrack needs the `lapx` fork *because* the stock `lap` C extension failed
   to build against this image's numpy (AVX-512 FP16 intrinsics);
3. `onnxruntime-gpu` is pinned to `1.20.2` for the CUDA-12.4 era.

A pip that can move numpy puts all three at risk for a five-second audio job.
And it would land **above** the Detectron2 compile in the layer stack, so every
subsequent rebuild pays for it — §5 measured that at ~13 minutes.

`gltf_image` is a non-starter for a duller reason: no ffmpeg, and no source
video mounted.

So: `beat_image` — `debian_slim` + `ffmpeg` + `librosa`, **CPU only**. It
rebuilds independently and can break nothing else. `propose_counts` is
**spawned** at the top of `run_clip` and collected after reconstruction, so its
cold start disappears inside the ~90 s the GPU is busy rather than being added
to every job's wall clock. On a 20 s clip the CPU work is seconds, which rounds
to nothing against the $0.076 the L40S pass costs.

Hand-off between stages is the pattern already in the file: a small JSON in the
results Volume, exactly like `performance.json` — this stage has the video, the
export stage has the timeline. `count_total` is re-derived at assembly time
against `sample_times_s[-1]`, never taken from the beat module, which only ever
saw ffprobe's container duration.

**Failure is never fatal at any link.** No audio track, a silent clip, an
ffmpeg error, fewer than two beats: all end as "no proposal", the field is
omitted, and the lesson ships with hand-set counts. A lesson with hand-set
counts is the product. A lesson that did not get made is not.

**Not run on Modal in this pass.** No GPU session was available, so the numbers
above are a local `ffmpeg → librosa → ProposedGrid → proposed_counts →
validator` run on a synthetic click track, and they are labelled as such. What
is unverified until a real Modal run: that `beat_image` builds, and the real
per-clip cost of the extra container. W11's own measurements on real clips
(solo-01 143.6 BPM at 0.93, solo-02 117.5 at 0.91, solo-07 129.2 at 0.94,
group-synced-01 117.5 at 0.95) are what the confidence figures should look like
in production.

---

## 16. Navigation is wired without a second clock

`<LessonNavigator>` is mounted in `apps/web/components/LessonViewer.tsx`,
driven by the `MotionResult` the page already loads.

**The video is still the only clock.** `requestVideoFrameCallback` →
`timeRef` → `mixer.setTime`, unchanged. The navigator is fully controlled: it
receives `timeS` and emits `onSeek`, and it owns no time of its own. W6's
`advance()` helper is exported and **deliberately not used** — it is for a host
that owns a synthetic clock, and this host does not.

Count-based looping is applied **inside the existing rVFC publish**, one
`currentTime = ` per wrap. That is frame-accurate and cannot drift across forty
minutes of repeats, because the time is *set*, never stepped. The obvious
alternative — a `timeupdate` listener — fires about four times a second and
would overshoot a loop edge by up to a quarter second, which is audible on an
eight.

What this replaced, in `apps/web`: a range-input whole-dance scrubber, a dancer
chip row, and an A–B loop whose own comment said this was coming ("snapping
loop edges to count boundaries belongs to the count strip, which is W6's
package"). Their CSS went with them. The branch is a net deletion in the app.

`space`, `L` and `←/→` moved out of the viewer's key map into the navigator's.
Two `window` listeners for one key both fire, so this is a deletion rather than
a duplication — and the arrow keys stepped a quarter-second as an admitted
stand-in for stepping a count, which they now do. `M`, `S` and `F` stay with
the viewer. Speed, mirror, follow and compare are passed into the navigator's
transport row through `children`, which is the seam W6 left for exactly this.

Two resolution findings, both new because this is the app's first cross-package
**value** import (`lib/motion.ts`'s was type-only, so the bundler never saw
it): Turbopack will not resolve above the project directory, so its root is now
the repo; and it does not map `./core.js` onto `core.ts`, so the six `.js`
specifiers inside `packages/navigation/src` are extensionless — which is what
`moduleResolution: bundler` wants anyway.

---

## 17. Where authored structure lives, and where the server store attaches

`apps/web/lib/structure.ts`, in `localStorage`, keyed per lesson.

**Why not a server store today: `OPEN-DECISIONS.md` D5 is open.** Authored
structure is per-learner by definition, and there is no learner to key it on
until D5 (none / magic link / OAuth) is decided. A server store would have to
invent an identity, which is the decision D5 exists to make.

`load` and `save` are the entire seam. Once D5 lands:

- `save` → `PUT /lessons/{clip_id}/structure`, identity from the session
- `load` → `GET` the same, falling back to the local copy so an offline or
  logged-out learner keeps working
- the local copy becomes a write-through cache, so no caller changes shape

One sub-question is **recorded rather than guessed at**: what happens when the
stored structure and the local one disagree. Last-write-wins is wrong for a
learner who authored parts on their phone during class. That needs deciding
when D5 is decided, not before.

**Retention note.** D6/D7 delete server-side artifacts; a browser's
localStorage is outside that promise. That is honest today only because nothing
in this blob is derived from the video — it is counts and part names the
learner typed. If anything person-derived is ever added, it becomes an artifact
D7 has to be able to delete.

**Manual always wins**, and it is checkable rather than implied: the stored
blob carries an `authored` flag, a saved structure always beats the proposal on
load, and the proposal is never re-applied once the learner has edited
anything.

---

## 18. The honesty surface

A proposed count 1 presented as a fact is precisely the failure this project
exists to guard against, and the count grid is **worse** for it than the mesh:
a learner who trusts a wrong count 1 practises the whole dance off the beat.

So the note lives **above the count strip and is always visible**, not inside
the `Counts and parts` disclosure — that disclosure is closed by default, and a
learner who never opened it would never be told. It disappears the moment the
learner edits anything, because still calling their own grid a guess is the
same lie reversed. Three branches, all reachable in a fixture:

| state | line |
|---|---|
| strong proposal | "Counts proposed from the music, at 120 a minute. Count 1 is a guess — set it under Counts and parts." |
| weak proposal (confidence < 0.5) | "Counts are a weak guess from the music, at 196 a minute, and the tempo may be double or half that. Set them under Counts and parts." |
| no proposal | "Counts are not set for this clip. The 120 a minute on screen is a placeholder, not the music — set count 1 and the tempo under Counts and parts." |

The 0.5 threshold sits just above the 0.4 the beat module caps *itself* at when
the tempo lands outside the plausible dance band, so every implausible-tempo
proposal reads as weak.

`proposed_counts.warnings` is **not** rendered verbatim. Those strings are the
producer's, written for a log (*"tempo 196 BPM is outside the typical 70-180
dance-practice range…"*) — wrong voice for §11, and the §5 ALL-CAPS rule would
reject "BPM" outright. `confidence` picks between two app-owned lines instead.

`packages/navigation`'s copy is now swept by `apps/web`'s §11 lint, which its
own header had asked for.

---

## 19. Test matrix

| Suite | Before | Now | Result |
|---|---|---|---|
| `packages/motion-contract` — TypeScript | 14 | **17** | **17 pass** |
| `packages/motion-contract/python` | 14 | **17** | **17 pass** |
| `packages/navigation` (`test/core.test.ts`) | 17 | 17 | **17 pass** |
| `packages/beat-detect/python` | 2 | 2 | **2 pass** |
| `apps/web` (`lib/*.test.ts` + `test/*.test.ts`) | 27 | 27 | **27 pass** |
| `services/motion-api/test_proposed_counts.py` (new) | — | **4** | **4 pass** |
| `services/motion-api/test_retention.py` | 10 | 10 | **10 pass** (2 extended) |
| `services/motion-api/test_api_rotations.py` | 6 | 6 | **6 pass** |
| `services/motion-api/test_grounding.py` | 15 | 15 | **15 pass** |

`apps/web`: `npm run build` and `tsc --noEmit` both clean; `packages/navigation`
`tsc --noEmit` clean. No test was loosened, skipped or deleted. The two changed
`test_retention.py` assertions were **tightened**: `.beats.json` is now seeded
into the fixture lesson, so the "survivors == [tombstone]" check fails if the
new artifact ever escapes the deletion path.

The CV and glTF suites under `services/motion-api/vendor` were not re-run —
nothing on this branch touches them, and they need `onnxruntime`/`filterpy`/
`pygltflib` plus a Python 3.11/3.12 environment. `integration-2`'s §10 numbers
stand for them.

---

## 20. Real-browser evidence that counts drive playback

Production build, real Chromium at `localhost:3311`, `/lesson/good-lesson`
(proposal: 120 a minute, count 1 at 0.400 s, 28 counts).

| Check | Measured |
|---|---|
| Counts follow the video clock | played from 0; at `currentTime` **3.052 s** the active count was **6**. The grid says `floor((3.052 − 0.4) / 0.5) + 1 = 6`. |
| Arrow steps a count, on the boundary | 2.000 → **2.400** → **2.900** — exactly `timeOfCount(5)` and `timeOfCount(6)` |
| Shift-arrow steps a part | → **4.400** = `timeOfCount(9)`, part line reads **"Part 2 · counts 9–16"** |
| Loop stays inside its counts | loop part 2 `[4.4, 8.4]` and part 3 `[8.4, 12.4]`, sampled once a second across repeated wraps: never outside; a wrap observed at 11.823 → 8.901 |
| Sections are semantic, never timestamps | "Part 3 · counts 17–24" — no `0:07–0:12` anywhere on the surface |
| The proposal is overridable | "Set count 1 here" at 4.40 s re-anchored the grid to **20 counts, count 1 at 4.40 s** |
| …and the override wins | the proposal note disappeared, the editor line flipped to "Set by hand — nothing here came from the music", and both survived a full reload out of `localStorage` |
| All three copy branches render | strong (`good-lesson`), weak (`failure-lesson`, 196 a minute), none (`two-dancers-apart`) |
| Console / network | no errors, no failed requests; one pre-existing three.js `PCFSoftShadowMap` deprecation warning |

**Two defects found by the browser that review had not.** Both are recorded
because neither is visible in a diff:

1. **The loop button lied about what it would do.** In "play all" the loop span
   was whatever was last set, so the button read "Loop part 1" while the
   playhead sat in part 2 — and looped part 2 when pressed. §8's state-in-label
   rule failing in its easiest place to miss: the label was true of the *state*
   and false of the *action*.
2. **The loop wrapped on its leading edge as well as its trailing one.** It
   looked symmetric and silently undid any deliberate seek before the loop, so
   dragging the overview bar in loop mode read as broken. Only the trailing
   edge wraps now, which is all §7 asks for.

---

## 21. Open, and deliberately not answered here

- **A4 (part editor)** and **A5 (count anchoring)** are still OPEN. Nothing
  gestural was invented: every edit on this surface is still a labelled button
  acting on the playhead, which is W6's own choice and the right default while
  the decision is open. What this branch *adds* to A5's brief, from having
  built against a real proposal: the correction UI has to handle a grid that is
  right about spacing and wrong about phase, which is the normal case rather
  than an edge one; and the half/double swap is a one-tap affordance the
  contract now carries the data for but nothing yet renders.
- **D5** blocks the server-side structure store (§17), including the conflict
  rule between a stored structure and a local one.
- **A real Modal run** of `beat_image` (§15).
- **§3.3 / §9.4's other open item** — W9's per-joint visibility, computed and
  discarded — is untouched by this branch and still unowned.

---
---

# Third integration pass — branch `integration-3`

Five more branches landed on top of the four `integration-2` merged. Same
exercise, same question: **what is broken only once the pieces meet?** This pass
found one defect of exactly that kind, and it is the same shape as §9.1's even
though nothing was moved between files this time: two branches edited two
*different* files, git had nothing to conflict on, every one of the 189 tests
stayed green, and the composed result would have deployed an API that answers
500 to every request while `modal deploy` printed success (§24.1).

Base: `origin/integration-2`. Nothing from `main` merged. No branch modified,
deleted or force-pushed. Every merge pushed before the next one started.
Everything below is measured on the merged branch, including a real Modal L40S
session and a live deploy of the HTTP service.

---

## 22. Merge order

Ancestry verified with `git merge-base` over every pair before starting rather
than trusted from the brief. **This time the brief's tree was correct** — the
two errors the first two passes found do not recur:

| # | Branch | Cut from | Verified | Result |
|---|--------|----------|----------|--------|
| 1 | `lesson-structure` | `integration-2` (`b31bea2`) | yes | clean |
| 2 | `hand-crop-view` | `lesson-structure` tip (`ff76b3a`) | yes | clean |
| 3 | `link-ingestion` | `integration-2` (`b31bea2`) | yes | 2 conflicts (§23.1, §23.2) |
| 4 | `grounding-wiring` | `link-ingestion` tip (`42eb96c`) | yes | clean; `motion_result.py` auto-merged and audited (§23.3) |
| 5 | `deployment` | `integration-2` (`b31bea2`) | yes | 3 conflicts, one of which is the whole point of this pass (§24.1) |

Dependency order, so the two stacked pairs go in as pairs: `hand-crop-view`
directly after its base `lesson-structure`, `grounding-wiring` directly after
its base `link-ingestion`. `deployment` last, because it is the branch that
edits the most of `api.py` and it is better to re-derive its changes onto four
merged branches than to have four branches land on top of it.

Every merge is a real merge commit (`--no-ff`), and **every merge was tested and
pushed before the next began** — five merges stacked and then debugged is how
the work gets lost.

| merge | commit |
|---|---|
| `lesson-structure` | `2e23688` |
| `hand-crop-view` | `05c7882` |
| `link-ingestion` | `42334f7` |
| `grounding-wiring` | `1839ab3` |
| `deployment` | `b49ecae` |

---

## 23. Conflict resolutions

### 23.1 `next.config.mjs` — two branches, two unrelated reasons, one file

`lesson-structure` sets `turbopack.root` to the repo, because
`<LessonNavigator>` is the first *value* import from a sibling package and
Turbopack will not resolve above the project directory. `link-ingestion` adds a
`rewrites()` proxying `/api/*` at the motion service, because the app had been
fetching `/api/jobs/...` from three places with nothing serving them.

Union, not a choice: the two keys are independent and dropping either breaks a
different feature. Both comment blocks kept, merged into one docstring that says
which half is which, because the next person to open this file will be adding a
third key and both reasons need to survive that.

### 23.2 `OPEN-DECISIONS.md` D5 — two branches append a different dependency

Both sides add a "this decision now blocks something new" note to the same D5
row. `lesson-structure`'s is that authored counts live in `localStorage` with
nothing to key them on; `link-ingestion`'s is that a link-derived `clip_id`
makes D11's takedown question depend on D5. Neither replaces the other. Both
kept, and `link-ingestion`'s renumbered from "Second dependency" to "Third",
which is the same clash §8.2 recorded for E-numbers: branches cut from one
commit pick the same next free ordinal against their own base. Nothing prevents
it and nothing yet does.

### 23.3 `motion_result.py` — the highest-risk file, auto-merged, audited anyway

`grounding-wiring` rewrites this file (+214/−43: the world-placement solve, the
camera-space grounding call, the `camera_to_world` rationale) while
`lesson-structure` adds `_proposed_counts` and a `beats` parameter to the same
function's signature. Git produced no conflict. Given that §9.1 was a clean
merge of this exact file that silently reverted four packages, "no conflict" is
not evidence of anything, so the merged file was diffed against **both** parents
rather than read for plausibility:

```
diff origin/grounding-wiring:motion_result.py  <merged>
  -> exactly four hunks, all additive, all lesson-structure's beats work
```

Nothing of `grounding-wiring`'s rewrite was dropped and nothing of
`lesson-structure`'s addition was. The composed `build_motion_result(job_id,
clip_id, npz_bytes, manifest, perf, beats=None)` carries both.

### 23.4 `modal_app.py` — four branches, no conflict, each edit verified present

`lesson-structure` (+100: `beat_image`, `propose_counts`, the spawn/collect pair
inside `run_clip`), `link-ingestion` (+13: the `results.reload()` guard before
`export_clip_gltf` reads the npz), `grounding-wiring` (+12: mounting
`world_placement_probe.py` and `skeleton_constraints.py` into `gltf_image`) and
`deployment` (+221: `api_image`, the `@modal.asgi_app()` web function, R2
secrets, `_publish_to_r2`) all edit this file in non-overlapping places.

Each was checked present in the merged file by name rather than assumed, because
the ENOENT fix in particular is the sort of four-line guard that a merge can
quietly lose: `link-ingestion`'s `if not os.path.exists(npz_path):
results.reload()` is at line 1231 of the merged file, still above the
`np.load`, and `lesson-structure`'s `beats` read is at 1448, still below it.
Both survived, in the right order.

### 23.5 `api.py` — three conflicts, and §24.1

`link-ingestion` (+279) and `deployment` (+168) both substantially rewrite this
file. Two of the three conflicts are unions (the import block: `Header` and
`ingest` from one side, `RedirectResponse`, `jobstore` and `storage` from the
other; and a helper-ordering collision where one side inserted `_publish_video`
exactly where the other split `_find_existing` into `_usable` +
`_find_existing` + `_find_by_source`). The third is §24.1.

---

## 24. What was broken only in combination

### 24.1 The deployed API would have 500'd on every request

**Severity: fatal in production, invisible in the merge and in every test.
Found and fixed.**

This is the finding this exercise exists to produce, and it is a cleaner
specimen than §9.1 because nothing was moved and nothing was claimed verbatim.
Two branches edited two different files, correctly, against their own bases.

* `deployment` adds `api_image` so `api.py` can run as an
  `@modal.asgi_app()` on Modal. It mounts `services/motion-api` with
  `ignore=["vendor/**", ...]`, and that exclusion is the *point* of the image:
  api.py's whole design property is that it never imports torch or the CV
  stack, so 1.9 GB of vendored Fast-SAM-3D-Body has no business in a CPU
  container. Correct when written — api.py had no vendored dependency at all.
* `grounding-wiring` gives `motion_result.py` a module-level
  `import world_placement_probe`, which itself has a module-level
  `import skeleton_constraints` — a file that lives under `vendor/`. Correct on
  its own base, which had no `api_image` in it. It even remembered to mount that
  file into `gltf_image`, the only image that existed to mount it into.

`api.py` imports `motion_result` at module level. Composed:

```
import api -> import motion_result -> import world_placement_probe
           -> import skeleton_constraints
ModuleNotFoundError: No module named 'skeleton_constraints'
```

**Git had nothing to conflict on** — two different files, no textual overlap.
**No test could have caught it**, and this is the part worth internalising: every
suite in this repo runs from a checkout where `vendor/` is simply *there on
disk*, so `import api` succeeds locally no matter what api_image ships. The
image even builds and `modal deploy` reports success, because a mount list is
not type-checked against an import graph. The failure surfaces only as a 500
from the live URL, on the first request after a container recycle.

Reproduced before fixing, by building api_image's file tree by its own rules
(three `add_local_dir` mounts with their ignore lists) into a temp directory and
importing `api` from it in a clean subprocess. That reproduction is now the fix's
test.

Fixed in `modal_app.py` with one mount: `skeleton_constraints.py` (17 KB, pure
numpy, no torch) put back at the exact repo-relative path it came from, so
`world_placement_probe`'s own `sys.path.insert(_HERE / "vendor/...")` finds it
with **no import-path change in any module**. The `vendor/**` exclusion stays,
which is what keeps api_image a CPU image. `gltf_image` mounts the same file
flat at `/app` because that image has a flat `/app`; the two mounts differ in
path for that reason and no other.

Covered by `services/motion-api/test_api_image.py`, two tests:

* `test_api_imports_with_only_what_api_image_ships` — builds the tree, imports
  `api` in a subprocess, fails with the ModuleNotFoundError if any future branch
  adds another unshipped import anywhere in that graph. Confirmed to fail when
  the mount is removed.
* `test_skeleton_constraints_is_mounted_despite_the_vendor_exclusion` — the
  named instance, so a failure reads as itself rather than as "something is
  unshippable".

**Verified on the real deploy, not only in the reproduction**: after
`modal deploy` and a forced fresh container, `GET /health` answers 200 and
`POST /clips/link` answers its 403. Both require `api.py` to have imported.

**The general lesson, since this will recur:** §9.1's was "a branch cannot claim
*verbatim* about a file it has not seen for four packages". This one's is
narrower and nastier: **a branch that adds an import and a branch that narrows a
deployment manifest cannot see each other at all.** Neither file appears in the
other's diff. The only thing that catches it is an import performed against the
manifest's own rules, which is why that is now a test rather than a habit.

### 24.2 `deployment`'s R2 publish and job record landed in a deleted function

**Severity: silent loss of two features on both front doors. Caught in the
conflict, re-derived.**

The third `api.py` conflict, and a direct echo of §9.1 in a new costume.

`deployment` adds two calls inside `upload_clip`: `_publish_video(clip_id,
tmp_path)` (so the source video is range-servable from R2 instead of proxied
whole through the service) and `jobstore.record_dispatch(...)` replacing the
raw `retention.write_json(... job-meta.json ...)`. Correct where that branch was
cut.

`link-ingestion`, meanwhile, had moved that entire function body out of
`upload_clip` into a new `_store_and_dispatch(tmp_path, clip_id, fp,
source_key)`, precisely so that the uploaded-file door and the pasted-link door
mint a job in exactly one place — which is what keeps a takedown complete.

Git offered the two `deployment` additions as non-overlapping edits to a
function the other side had deleted. **Taking that offer would have dropped R2
video publishing and the jobstore record from both front doors**, with no
conflict marker on those lines, no failing test, and a `/health` that keeps
saying `"assets": "r2"` because R2 *is* configured — the videos simply would
never have been put in it. Every lesson would have silently regressed to the
byte proxy that cannot answer a `Range:` request, i.e. video scrubbing, which is
DESIGN.md §7c's core interaction.

Re-derived into `_store_and_dispatch` instead of replayed. The composed result is
strictly better than `deployment`'s own: the **link door now gets both for
free**, so a linked lesson's video is range-servable exactly like an uploaded
one, which `deployment` could not have written because `/clips/link` did not
exist on its base.

One thing deliberately **not** converted while re-deriving: the adoption read at
the end of `_store_and_dispatch` stays a raw Volume read of
`{job_id}.job-status.json` and is **not** switched to `jobstore.read_status`,
even though every other status read in the file was. It asks one question — "has
`run_clip` started and written its own status document" — and only the worker
writes that document. `record_dispatch` a few lines above inserts a `queued` row
for *this* request under `STEPWISE_JOB_BACKEND=postgres`, so reading the row back
here would find our own insert and adopt a job nobody ever spawned. The comment
in the code says so, because the next person to tidy this will reach for the
abstraction.

### 24.3 A stale container kept serving pre-merge code after `modal deploy`

**Severity: not a defect. Confirmed behaviour, recorded because it invalidates
the obvious way to verify a deploy.**

The brief flagged this and it reproduced exactly. After `modal deploy` of the
merged branch (50.7 s, mounts only, no image rebuild):

```
GET  /health       -> 200   {"ok":true,"assets":"r2",...}
POST /clips/link   -> 404   {"detail":"Not Found"}
```

`/clips/link` exists only on merged code, and its invite gate answers **403**,
never 404 (deliberately — "someone who was given a code and typed it wrong"
deserves to be told). A 404 is therefore proof the ASGI app being served predates
the merge. `/health` answering 200 the whole time is the trap: the endpoint that
looks like a deploy check is exactly the one that cannot tell you the deploy
took.

`modal container stop -y <id>` forces a fresh one, after which:

```
POST /clips/link   -> 403   {"error":{"code":"invite_required", ...}}
GET  /health       -> 200
```

So: when only mounted local files change, **the running container survives the
deploy**. Verifying a mount-only deploy requires either stopping the container or
probing something the new code alone can answer. `/health` is not that thing.
(This is also what turned §24.1 from a reproduction into a live verification —
the fresh container had to import `api.py` for real.)

### 24.4 Smaller notes

* **`beat_image` had never run on Modal.** §15 recorded that as open. It ran
  here, in parallel with reconstruction as designed: `[beats] solo-01: 143.6
  BPM, 0.4180 s/count, count 1 at 0.070s, confidence 0.91`, emitted while the
  GPU was still on frame 1 of 296. The whole cost disappeared inside the GPU
  stage exactly as §15 argued it would, and no image rebuild was triggered.
* **`api.py` carries a dead import.** `from grounding import
  camera_intrinsics_from_clip, solve_grounding_for_clip` (line 79) is used
  nowhere in the file — a leftover from `caching-retention` moving the assembly
  into `motion_result.py`. Harmless, pre-existing on `integration-2`, and left
  alone rather than tidied mid-merge. Worth naming only because if it *were*
  live it would now be a second, character-space grounding solve sitting beside
  `motion_result`'s camera-space one.
* **`test_schema.py`'s 12 tests skip by default** (no `DATABASE_URL`) and the
  skip is correct — they must not fail on a laptop with no container daemon.
  They were not left skipped here: run against a real `postgres:16` container,
  all 12 pass, including the one that matters (a job-status document served from
  a row is byte-identical to one served from the Volume). `requirements-api.txt`
  correctly pins `psycopg[binary,pool]`; installing only `psycopg[binary]` fails
  five of them on `psycopg_pool`, which is worth knowing when reproducing.
* **The "4 Issues" badge is explained and survives.** It is the Next.js **dev
  overlay**'s issue counter, and its four entries are four
  `THREE.WebGLRenderer: A WebGL context could not be created` console errors
  raised from `Stage3D.tsx:542`, because the headless browser taking the
  screenshot has no GPU. It is dev-only (absent from `next build` output) and an
  artifact of how the screenshots are taken, not of the page. Still out of
  scope, but no longer unexplained.

---

## 25. Test matrix

Every suite in the tree, on the merged branch. Python 3.12, Node 24.

| Suite | `integration-2` | Now | Result |
|-------|-----------------|-----|--------|
| `packages/motion-contract` — TypeScript (`test/ts/validate.test.ts`) | 14 | **17** | **17 pass** |
| `packages/motion-contract/python` (`tests/test_validate.py`) | 14 | **17** | **17 pass** |
| `packages/navigation` (`test/core.test.ts`) | 17 | 17 | **17 pass** |
| `packages/beat-detect/python` (`tests/test_propose.py`) | 2 | 2 | **2 pass** |
| `apps/web` — `test/copy.test.ts` | 10 | **14** | **14 pass** |
| `apps/web` — `test/logic.test.ts` | 4 | 4 | **4 pass** |
| `apps/web` — `lib/motion.test.ts` | 13 | **14** | **14 pass** |
| `services/motion-api/test_grounding.py` | 15 | 15 | **15 pass** |
| `services/motion-api/test_world_placement_wiring.py` (new, `grounding-wiring`) | — | **9** | **9 pass** |
| `services/motion-api/test_api_rotations.py` | 6 | 6 | **6 pass** |
| `services/motion-api/test_proposed_counts.py` (new, `lesson-structure`) | — | **4** | **4 pass** |
| `services/motion-api/test_ingest.py` (new, `link-ingestion`) | — | **23** | **20 pass, 3 skipped** |
| `services/motion-api/test_schema.py` (new, `deployment`) | — | **12** | **12 pass** |
| `services/motion-api/test_api_image.py` (new, §24.1) | — | **2** | **2 pass** |
| `services/motion-api/test_retention.py` | 10 | 10 | **10 pass** |
| `services/motion-api/test_fingerprint.py` | 2 | 2 | **2 pass** |
| `services/motion-api/tools/test_region_mask.py` | 9 | 9 | **9 pass** |
| `tools/test_skeleton_constraints.py` | 12 | 12 | **12 pass** |
| `tools/test_hand_crops.py` | 8 | 8 | **8 pass** |
| `tools/test_smoothing.py` | 9 | 9 | **9 pass** |
| `tools/test_process_clip.py` | 5 | 5 | **5 pass** |
| `tools/test_rtmo_detector.py` | 7 | 7 | **7 pass** |
| **Total** | **157** | **238** | **235 pass, 3 skipped, 0 fail** |

157 → 238 is +81: contract +3/+3 (`proposed_counts`, both sides), `copy.test.ts`
+4 and `motion.test.ts` +1 (the web branches), `test_ingest.py` +23,
`test_schema.py` +12, `test_world_placement_wiring.py` +9,
`test_proposed_counts.py` +4, and +2 written here for §24.1.

**Nothing was loosened, skipped or deleted.** The two additions are both §24.1's
guard; both were confirmed to fail when the mount they protect is removed.

**The three skips are honest and were left as the branch wrote them.**
`test_ingest.py`'s three live-network tests are gated on `STEPWISE_LIVE=1` and
hit TikTok for real — they are not runnable in CI by design.

**`test_schema.py` was NOT left skipped.** Its twelve tests skip when
`DATABASE_URL` is unset, which is correct for a laptop with no container daemon,
but "skipped" is not "green". Run against a real `postgres:16`:

```
docker run -d --name stepwise-pg -p 5433:5432 -e POSTGRES_PASSWORD=stepwise postgres:16
DATABASE_URL=postgresql://postgres:stepwise@localhost:5433/postgres \
  python3 -m pytest test_schema.py -q        -> 12 passed
```

**Reproducing the Python suites.** As §10, plus: `librosa` + `soundfile`
(beat-detect), `boto3` (storage), `psycopg[binary,pool]` — the `pool` extra is
load-bearing, `psycopg[binary]` alone fails five `test_schema.py` tests on
`psycopg_pool`. `test_world_placement_wiring.py` additionally needs
`vendor/fast-sam-3d-body/tools` on `PYTHONPATH` (that is what §24.1 is about).

**`apps/web`**: `npm run build` and `tsc --noEmit` both clean. `npm run assets`
must run first. Routes built: `/`, `/upload`, `/job/[jobId]`, `/lessons`,
`/lesson/[lesson]` ×6.

---

## 26. End-to-end on Modal

`modal run modal_app.py::run_clip --clip-id solo-01` on the merged branch. Real
L40S session, real clip, real GLB. App `ap-snkLndtJcLp3nsh9dkAOGw`, job
`job_solo-01_1789989003`, final job-status document:

```json
{"schema_version": "1.0.0", "job_id": "job_solo-01_1789989003",
 "state": "succeeded", "stage_message": "", "progress": 1.0,
 "error": null, "retry_count": 0}
```

### Cost and runtime

| | This pass | `integration-2` | First pass |
|---|---|---|---|
| Reconstruction | **82.9 s (3.57 fps)**, 291/296 frames | 87.1 s (3.40 fps) | 146.5 s (2.02 fps) |
| Wall clock incl. export | **136.0 s** | 140.9 s | — |
| Peak VRAM | **3.69 GB** | 3.69 GB | 3.69 GB |
| **Cost** | **$0.0737** | $0.0763 | $0.1279 |
| Image build | none — mounts only | none | ~13 min |

3.57 fps against `GATE-REPORT.md`'s 3.79; the same note applies as in both prior
passes, and the trend across three runs on warm containers is flat.

### The merged pipeline, in the order it ran

```
[beats] solo-01: 143.6 BPM, 0.4180 s/count, count 1 at 0.070s, confidence 0.91
done: 291/296 frames reconstructed, 82.9s total (3.57 fps), peak VRAM 3.69 GB
  bone lengths, track 1: 117 bones fixed, worst frame off by 2.36x,
    177/291 frames carry an uncertain joint
  crops, track 1: hands 289/291 frames, feet 278/291 frames
  smoothing track 1: 27363 observed, 9204 uncertain, 1025 absent (28 impossible)
SAVED /results/solo-01.npz
wall clock: 136.0s  pipeline-internal: 82.9s
track 1: 291/296 samples observed (first at 1, leading gap back-filled)
track 1: shape from 291 frames, ||shape||=2.846, rest-mesh mean=0.2492 max=2.1353 cm
SAVED solo-01_track1.glb (single mesh, pre-region-split)
track 1: region triangle counts: {18 regions, all non-zero}
SAVED solo-01_track1.glb (region-split)
SAVED solo-01_track1.glb (region-split, 218/218 samplers rewritten to LINEAR)
[grounding] solo-01: grounded -- {...}
[beats] solo-01: 143.6 BPM, 47 counts, confidence 0.91
[r2] published 2 objects for solo-01
[job-status] succeeded 1.0
```

The `[beats]` line is first because `propose_counts` is **spawned** beside the
GPU work rather than sequenced after it — `lesson-structure`'s §15 design,
running on Modal for the first time. §2.2's stage order (spatial → crops →
temporal) and §8.1's post-export order (region split → interpolation rewrite)
both survive four more merges.

### Verification of the exported GLB

Measured on the downloaded file, not read from the log. Reproduce:
`python services/motion-api/verify_glb.py <file.glb> --expect-fps 15.0`.

| Check | Result |
|---|---|
| Verdict | **PASS** |
| GLB produced | yes, **1,937,604 bytes**, 1 animation, 218 channels |
| **Interpolation** | **LINEAR on 218/218 samplers. Zero STEP.** |
| **Keyframe rate** | **15.0 fps** (dt = 0.066667 s) |
| **Non-finite animation values** | **0 / 222,296** |
| **Non-finite mesh vertices** | **0 / 30,498 components** |
| **Region meshes** | **18 / 18 present and named `region_*`, none empty** |
| Shape bake applied | yes — 291 observed frames, `‖shape‖ = 2.846`, rest-mesh 0.2492 cm mean / 2.1353 cm max |
| Bone-length CV | mean 2.1503%, **median 0.0001%**, max 74.0848%, 72/119 under 0.01% |
| Animated `scale` nodes | `l_wrist`, `r_wrist` — the same two, the same cause |

Bone CV is the third independent measurement of the same distribution (2.1426 /
0.0002 / 73.7855 / 72, then 2.1504 / 0.0002 / 74.0992 / 72, now 2.1503 / 0.0001 /
74.0848 / 72). Pre-existing, `bone-constraints`' call, untouched here.

### Verification of the served MotionResult

Measured on the downloaded `solo-01.motion-result.json.gz`, materialised by the
GPU worker (not rebuilt by `api.py`):

```
MotionResult VALIDATES against the frozen v1 schema
persons=1  samples=296  joints=127
non-finite numbers anywhere in document: 0
grounding.status = grounded
  floor_plane.normal = [-0.016115, 0.973953, -0.226177]
  floor_plane.point  = [-0.046584, -0.963417, -3.483641]
camera.intrinsics.fx = 1174.88     (real estimate, not the 1024.0 placeholder)
camera_to_world = identity
proposed_counts = {bpm 143.55, s/count 0.41796, count 1 at 0.0697s,
                   count_total 47, confidence 0.905,
                   alternates: double-time 287.1, half-time 71.8}
person 0.animation = {'clip_id': 'solo-01_track1',
                      'glb_asset_id': 'solo-01_track1.glb'}
person 0.shape_params.source = well_observed_frames   (vector withheld)
person 0.crop_rects.hands = 289/296, .feet = 278/296
document = 7,162,777 characters
```

Every package is visible in one document at once: W8's per-person `animation`,
`shape-params`' honest `source` with `caching-retention` still withholding the
vector, `hands`' crop rects, `grounding`'s real intrinsics, `grounding-wiring`'s
floor solve, and `lesson-structure`'s `proposed_counts`.

**`grounding.status` is `grounded`, not `none`.** This is the first run in three
passes where it is. The diagnostics:

```
n_inliers 69, inlier_rms_m 0.01646, tilt_deg 13.106, floor_height_m -0.9634,
contact_time_coverage 0.80 (16 s of a 20 s clip), foot_visible_fraction 0.9622,
planted_frame_fraction 0.5357, reason "grounded"
```

The thing that changed is not the floor solver's thresholds — those are
unchanged (`min_time_coverage` still 0.6). It is that `grounding-wiring` feeds
it `world_placement_probe`'s real per-frame camera-space translations instead of
the character-local frame's flattened depth. §5 and §11 both recorded `none` with
`reason: contacts_not_spread_over_clip` at 0.30 coverage; the same clip now
reaches 0.80.

**Travel, measured on `root_trajectory` rather than claimed:**

```
XZ travel extent      8.626 m
depth span (Z)        8.253 m
path length           27.35 m
vertical span (Y)     1.881 m
distinct root positions   276 / 296 samples
root provenance observed  287 / 296 samples
```

Against `integration-2`, where every one of the 296 positions was the identical
constant `(0, 0.924, 0)`. This is E6's 8.7 m of depth showing up in the shipped
document, and it agrees with `grounding-wiring`'s own pre-merge measurement of
8.25 m.

### `[r2] published 2 objects` — and the redirect actually works

The GLB and the gzipped MotionResult were published to R2 by the export stage.
Checked end to end against the **live** service, on an artifact this run
produced:

```
GET /assets/solo-01_track1.glb -> 302
   -> https://<acct>.r2.cloudflarestorage.com/stepwise-results/glb/solo-01_track1.glb?X-Amz-...
   Range: bytes=0-1023  ->  HTTP 206, 1024 bytes
```

206 with exactly the requested bytes is `deployment`'s whole argument working on
merged output: the old byte proxy could only answer 200 with the entire file.

### npz slimming survived four more merges

`solo-01.npz` is **4,415,899 bytes** (4,416,302 on `integration-2`; 61.30 MB
before `caching-retention`). `pred_vertices` and `expr_params` are absent;
`per_frame`, `sample_times_s`, `raw_detections`, `frame_width`/`frame_height`
(which `world_placement_probe` now requires) and W9's whole `smoothed` block are
all still there.

---

## 27. Known open items — status, not fixes

All four were re-checked on the merged branch against this run's artifacts.
**None was fixed here**; three are unchanged and one is now measurable.

* **The exported GLB still carries the character-local root.** Confirmed, and it
  is the one place the document and the GLB now disagree: `root_trajectory`
  carries 8.6 m of travel while the GLB's root channel does not, and
  `Stage3D` animates the GLB and never reads `root_trajectory`. So the *rendered*
  dancer still dances in place. This is recorded as E6 item 5 and is the next
  work package, not this one.
* **W9's per-joint visibility is still computed and still discarded** (§3.3,
  §9.4). Now with both halves measured on the same run, from the same artifacts:

  ```
  npz `smoothed` block: 198 / 296 frames carry more than one distinct
                        per-joint visibility value
  served MotionResult:    0 / 296 frames do
  ```

  The pipeline works out per-joint occlusion on 198 frames and throws it away on
  all 198. The hookup point is unmoved (`motion_result.build_motion_result`
  reads `data["per_frame"]`, never `data["smoothed"]`). Still a product
  decision, still unowned.
* **Bone CV is not 0.0000%.** Median **0.0001%**, mean 2.1503%, and the fingers
  are still below `l_wrist`/`r_wrist` — the only two nodes in the file carrying
  an animated `scale` channel. Third identical measurement, pre-existing,
  `bone-constraints`' call.
* **The "4 Issues" badge survives** — and is explained in §24.4. It is the
  Next.js dev overlay, counting four WebGL-context errors raised because the
  headless screenshot browser has no GPU. Dev-only, absent from `next build`.

### Three stale comments, now fixed

`grounding-wiring` deliberately left three comments claiming `root_trajectory`
is pinned, because the files were being edited concurrently by the two web
branches. After merge nothing else is in flight in those files, so they are
fixed here — comments only, no behaviour change:

* `apps/web/lib/motion.ts` — `travelExtent`'s "~0.2 m on every real clip". The
  gate it justifies is still right, for a *different* reason, which is what the
  new note says: a track under 25 frames still falls back to the pinned
  constant, so one document can carry a real trajectory and a placeholder.
* `apps/web/components/LessonViewer.tsx` — the follow-camera rationale. Rewritten
  to point at the seam that is actually still open (GLB root, above) rather than
  at one that closed.
* `apps/web/lib/lessons.ts` — the synthetic-travel fixtures. Still the only
  fixtures here with travel in them, but because nobody has checked in a real
  placed clip, not because the pipeline pins anything.

A fourth, unlisted, was found and fixed with them: `LessonViewer.tsx`'s
follow-button comment asserted grounding is `"none"` on *every* real clip, which
this run disproves.

---

## 28. Ground rules honoured

- Work only on `integration-3`, cut from `origin/integration-2`. **Pushed after
  every one of the five merges**, not once at the end.
- `main` never merged. No force-push. No branch modified, renamed or deleted —
  `lesson-structure`, `hand-crop-view`, `link-ingestion`, `grounding-wiring` and
  `deployment` are untouched commits that were read from.
- `docs/DESIGN.md` and `docs/OPEN-DECISIONS.md` carry only the edits the merged
  branches made to them, plus §23.2's D5 renumbering. **This pass opened no
  decisions of its own and closed none.** E6 in particular is left OPEN with
  `grounding-wiring`'s own five-item list of what the wiring did *not* resolve,
  because absolute metric scale, the viewer render, and short-track
  trustworthiness are still unverified and answering them is not a merge's job.
- No secret committed. R2 and database credentials are Modal Secrets read at
  runtime; `/health` reports which names are set and never a value.

---

## 29. integration-4

**Cut 2026-09-23 from `render-travel` at the commit that adds this section**,
fast-forward from `integration-3` (`dd490fc`). No merges were needed: every
change since integration-3 landed on one line of history.

| Commit | What |
|---|---|
| `8230189`, `88fe3c2` | E6 item 5, route B: `Stage3D` places each dancer from `root_trajectory`. Closes §27's first bullet — the rendered dancer now travels. |
| `4731bbe`, `92d508f` | CI typechecks `apps/web` with `packages/navigation` installed; `apps/web` packaged as a Cloudflare Worker (OpenNext). |
| `8081567`, `c620bf3` | Sentry, backend and browser. `c620bf3` fixes the switch-on deploy, which crashed every container (DEPLOYMENT.md §5.3). |
| `deadd04` | `/lesson/{id}` resolves in the browser: fixtures from `/fixtures`, anything else as a job via `/api`. Real lessons no longer 404, and there is no `node:fs` for the Worker to 500 on. |
| `19cbd2f` | Dispatch rate limit in Postgres: 5/h and 20/day per IP, 200/day overall, 429 in DESIGN.md §11's voice. |
| `31395a8`, `4669792` | `GET /jobs/{id}`: 404 for an id never dispatched, and the Postgres row no longer masks the worker's progress (every job since the cutover had read `queued` forever). |

**Browser-verified on this tip** (`next dev`, headless Chromium):

* `travelling` — top view, follow off: the dancer is at the left edge at 0.5 s
  and near centre at 12 s. The follow button reads "travels 2.6 m".
* `unplaced-dancer` — both dancers render standing on the floor. Dancer 2,
  whose placement never ran, stays where its clip puts it rather than at the
  2.16 m placeholder height, which is 88fe3c2's "visible limitation, not a
  confident lie" contract.
* A real eval clip (`solo-02`, 33 s, one dancer) end to end on the live
  Modal app: `POST /clips` → 214 s wall clock → `succeeded`, grounded,
  117.5 BPM. That run is what found the stuck-`queued` bug above, and that
  **R2 credentials are currently rejected** (DEPLOYMENT.md §1).

§27's other three items are unchanged.
