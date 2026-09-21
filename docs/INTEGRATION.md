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

Not wired here deliberately. It is a two-line lookup, but it changes what every
lesson renders — occluded limbs would start disappearing — and that is a
product-visible behaviour change that should be made and validated by the people
who own the suppression thresholds, not slipped into an integration merge. The
hookup point is `api.py:241`: read `data["smoothed"].item()` alongside
`data["per_frame"]` and take the per-joint arrays from it when the track is
present.

### 3.4 Smaller notes

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

<!-- RUN RESULTS -->

---

## 6. Ground rules honoured

- Work only on `integration`, cut from `origin/rebuild-v4`. Pushed.
- `main` never merged. No force-push. No other branch touched, renamed, or
  deleted.
- `docs/DESIGN.md`, `CLAUDE.md` and `docs/OPEN-DECISIONS.md` carry only the
  edits the merged branches already made to them; this integration pass added
  no new decisions to them of its own.
