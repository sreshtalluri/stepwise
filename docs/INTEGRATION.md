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
  touches it.

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
