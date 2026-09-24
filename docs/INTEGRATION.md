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

> **CLOSED 2026-09-20, branch `lesson-structure`.** All four links now exist.
>
> - **Contract.** `MotionResult.beat_proposal` — optional, top level, sibling of
>   `grounding` and `accent_color`, the document's two other machine estimates
>   about the clip. It carries the whole guess (`confidence`, `bpm`,
>   `alternates`, `warnings`), all required when the object is present, so a
>   bare grid that reads as fact is not a document a producer can emit.
>   Additive and optional, so `schema_version` stays `1.0.0` — under the
>   versioning rule now written down in `packages/motion-contract/README.md`,
>   which this change forced and which also records §3.1's `animation` move as
>   the bump-class change it was.
> - **Pipeline.** `modal_app.py::propose_beats` on its own CPU image, called by
>   `run_clip` after reconstruction, writing `{clip_id}.beats.json` beside the
>   npz; `api.py` attaches it when assembling the document. A separate image and
>   not two lines in `cv_image` for a reason that only showed up on the first
>   build: **librosa 1.0.0 requires Python ≥3.12 and `cv_image` is pinned to
>   3.11** by Detectron2 (PRD G3). Installing it there cannot give you the
>   library W11 measured on — pip silently resolves 0.11.0 instead, a different
>   beat tracker, and every proposed count 1 moves.
> - **Viewer.** `apps/web` renders `<LessonNavigator>`, and the duplicated
>   transport/chips/scrub bar §3.4 describes are deleted rather than left beside
>   it. The video stays the only clock: the navigator is given `timeS` from
>   `useVideoClock` and calls back into `video.currentTime`; the package's
>   `advance()` helper is deliberately unused, since running it would be the
>   second clock. Two config lines were needed —
>   `turbopack.root` (this app is a workspace in a repo with no root
>   `package.json`, so Next confined resolution to `apps/web`), and dropping the
>   `.js` suffixes inside `packages/navigation` (legal under its
>   `moduleResolution: "bundler"`, and Turbopack has no `.js`→`.ts` rewrite).
> - **Authored structure.** Client-side, `localStorage`, keyed per lesson
>   (`apps/web/lib/lessonStructure.ts`), because D5 leaves no server-side
>   identity to key it by. `restore()`/`save()` are the entire seam a server
>   store attaches to later, with no contract change.
>
> One real bug this surfaced, of exactly §3.1's shape — a true statement that
> silently became false when the thing below it changed. The counts editor read
> *"Nothing here was detected from the music."* That was written when detection
> did not exist; the moment `beat_proposal` started seeding the grid it became a
> false claim about where a number came from, which is the §7h failure mode
> stated backwards. `isStillProposed()` in `packages/navigation/src/core.ts` is
> now the single place that answers "machine or human", and both the editor
> summary and the viewer's honesty line ask it.
>
> Verified on real hardware: `modal run modal_app.py::propose_beats --clip-id
> solo-01` produced `143.6 BPM, 0.4180s/count, count 1 at 0.070s, 47 counts,
> confidence 0.905`, and that document validates against the frozen contract.

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
