# Agent briefs — copy-paste prompts

Each brief is self-contained. A fresh agent knows nothing about this project, so
do not trim them. Fire the ones marked READY now; the rest list their blocker.

**Repo:** `github.com/sreshtalluri/stepwise`, branch `rebuild-v4`.
**Read order for every agent:** `docs/PRD.md` → `docs/DESIGN.md` → `docs/OPEN-DECISIONS.md`.

---

## Standing rules — paste into EVERY brief

```
GROUND RULES

1. Read docs/DESIGN.md before any visual decision. This is enforced by CLAUDE.md.
2. Honesty boundary (docs/DESIGN.md §7h) — get this exactly right:
   - A dancer TURNING AWAY is tracked. Orbiting to see them is legitimate and is
     the best thing this product does. Do not undersell it.
   - A part that was BLOCKED or OUT OF FRAME was not recovered. Never imply it was.
   Both overclaiming and underclaiming have already happened in drafts.
3. docs/OPEN-DECISIONS.md lists 25 genuinely unresolved items. If your task hits
   one, STOP and ask. Do not invent an answer.
4. Measure, do not trust. Published FPS and cost figures in the PRD are vendor
   claims on different hardware; several could not be re-verified.
5. The builder hand-writes core algorithms (the adapter, the Kalman filter,
   grounding, suppression logic). You write scaffolding, tests, and plumbing,
   and you review his work. Do not write those cores for him.
6. Never commit secrets. .env is gitignored; real credentials live in Modal
   secrets and ~/.stepwise-secrets/.
7. Work on a branch, push it, and report what you did. Do not merge to main.
```

---

## W3 — MotionResult contract + fixture  🔴 FIRE FIRST, unblocks four other agents

```
You are building the data contract for stepwise, an open-source web app that
turns a dance video into an interactive 3D lesson.

Repo: github.com/sreshtalluri/stepwise, branch rebuild-v4. Clone it and read
docs/PRD.md sections 3 and 6, plus docs/DESIGN.md sections 4 and 7.

YOUR TASK: build packages/motion-contract — the frozen, versioned contract
between the GPU pipeline and the web app, plus a realistic fixture.

This is the highest-leverage task in the project: four other agents build
against your fixture, so getting it wrong means they all rework.

DELIVER:
1. A JSON Schema for MotionResult v1 at packages/motion-contract/schema/
2. Generated TypeScript types and Python dataclasses/pydantic models
3. A hand-written fixture at packages/motion-contract/fixtures/ representing ONE
   plausible finished lesson: ~14 seconds, one dancer, 30 counts, at 15fps
   sampled. Include realistic joint data — it must be good enough that a viewer
   built against it looks correct.
4. A second fixture exercising failure: some frames suppressed, feet cropped for
   part of the clip, grounding_status "none".
5. A validator that checks a MotionResult against the schema.
6. Tests.

THE CONTRACT MUST INCLUDE (these were identified in review as the fields most
likely to be missing and force a breaking rewrite):
- schema_version
- sample_times_s — the timestamp of EVERY sample on the normalized video
  timeline, including failed ones. Array index plus nominal fps is NOT
  sufficient; it breaks the moment a frame drops, and it affects playback,
  seeking, visibility and re-entry. This is the single most important field.
- Array shapes and axis order stated explicitly for every tensor
- Joint hierarchy, rest pose, and rotation convention
- Joint-to-GLB-node mapping, and the animation clip id
- PER-JOINT provenance, kept SEPARATE from visibility. A sample can be
  model-estimated AND interpolated AND suppressed simultaneously. Values:
  observed / interpolated / suppressed:out_of_frame / suppressed:low_confidence
  / suppressed:occluded / unknown. No inferred 3D joint may be labelled
  "observed".
- Nullable confidence, with its meaning defined in a comment
- camera_model (MVP is "single_front_static") and a per-axis uncertainty note —
  depth along the viewing axis is the least certain dimension
- grounding_status: static_floor | none, plus the floor plane equation or null
- Normalized video dimensions and orientation, and the audio offset
- Camera intrinsics and the camera-to-world transform
- Root trajectory per person
- Crop rectangles for the hands and feet close-up views
- Immutable asset ids, kept separate from expiring signed URLs
- Per-clip accent colour (the UI samples a colour from the video)
- model_report: model versions and licence flags
- A SEPARATE job status / error / retry contract

Also provide fixtures covering: mid-playback dropout, seeking, and re-entry
after a gap.

[PASTE GROUND RULES HERE]
```

---

## W2 — Licence compliance packaging  🟢 READY, small, independent

```
You are doing licence compliance for stepwise, an open-source project at
github.com/sreshtalluri/stepwise, branch rebuild-v4.

Read docs/PRD.md section 2 (specifically G2) first.

CONTEXT: this project depends on Meta's SAM 3D Body, distributed under the
custom "SAM License" — NOT an OSI-approved licence. It imposes obligations that
pass through to anyone who receives this work. Ultralytics YOLO was deliberately
dropped and replaced with RTMO (Apache-2.0) because AGPL-3.0 and the SAM License
cannot legally be combined in one program.

YOUR TASK: make this repo's licensing correct and legible.

DELIVER:
1. A clearly marked directory for SAM Materials containing a VERBATIM copy of
   the SAM License agreement. Its section 1.b.i requires derivatives carry it.
2. A NOTICE file.
3. docs/LICENSES.md mapping every single dependency to its licence, with a
   column for any obligation it creates. Cover at minimum: rtmlib/mmpose
   (Apache-2.0), ByteTrack upstream (MIT), Fast-SAM-3D-Body (MIT),
   SAM 3D Body (SAM License), MHR (Apache-2.0 — but VERIFY the asset licence,
   which ships INSIDE the assets.zip release download and has not been read
   yet), momentum/pymomentum (MIT), three.js (MIT), Next.js, React.
4. A README licensing section stating plainly: code written here is MIT,
   SAM-derived parts are under the SAM License, the repo as a whole CANNOT
   honestly be labelled MIT or Apache.
5. State the ITAR/military-use prohibition and the research-citation obligation.
6. A top-level LICENSE file for the original code (MIT).

IMPORTANT NUANCE: the citation obligation applies to research publications, not
to the hosted service. Do not overstate it. Similarly, making the repo public is
the builder's choice, not a licence requirement.

Flag anything you find that contradicts docs/PRD.md — a previous review found
two factual errors in it.

[PASTE GROUND RULES HERE]
```

---

## W1 — The feasibility gate  🟡 BLOCKED on HF token + Modal billing

```
You are running the feasibility gate for stepwise — deciding whether the core
technical premise works before ~70 more hours get committed.

Repo: github.com/sreshtalluri/stepwise. Start from branch worktree-modal-gate,
which already has working Modal infrastructure at services/motion-api/modal_app.py.
Read services/motion-api/README.md and docs/PRD.md sections 2 and 3 in full.

ALREADY DONE: Modal app with three staged functions, image verified to build
with torch 2.5.1/cu124, CPU stages green.

YOUR TASK, IN THIS ORDER. Stop at the first failure and report.

1. Confirm weights downloaded into the Modal Volume, and run inspect_weights to
   see which checkpoint variants exist and their sizes.
2. Run verify_gpu. Record the actual CUDA version, device, and free VRAM.
3. Build the real CV image. Pins are NOT arbitrary: Python 3.11, Torch 2.5.1,
   cu124, because Detectron2 compiles against that toolkit.
   - Fast-SAM-3D-Body's setup_env.sh STILL INSTALLS Ultralytics, TensorRT and
     SMPL-X. Remove all three; we use RTMO instead and TensorRT is not needed
     yet (rtmlib has no TensorRT branch).
   - Detectron2 fails if the image lacks nvcc or CUDA_HOME mismatches. Compile
     only after Torch is final.
   - Do NOT install pymomentum here. Its wheels target Python 3.12/3.13 with
     Torch 2.8 and are incompatible. glTF export gets a SEPARATE image; the two
     exchange plain arrays (npz/JSON).
4. Get RTMO running via rtmlib with ONNXRuntime CUDA. Import torch BEFORE
   creating the ORT session, and verify CUDA actually activated rather than
   silently falling back to CPU. Start with RTMO-m/body7 at 640x640.
5. Build the detector adapter. This is the crux and rtmlib will not hand you
   what you need:
   - RTMO(image) returns keypoints (N,17,2) and scores (N,17). Its postprocessor
     COMPUTES person boxes and detection scores and then DISCARDS them. Subclass
     it to retain the post-NMS boxes.
   - On zero detections it FABRICATES a single all-zero pose. Return genuinely
     empty arrays instead.
   - Concatenate keypoint confidence to produce (N,17,3).
   - Keep to_openpose=False so wrists stay at COCO indices 9 and 10.
   - Lower RTMO's default 0.7 threshold so ByteTrack still receives low-score
     candidates, and do not let ByteTrack rescale coordinates a second time.
   - Expose it as run_human_detection() returning
     {"boxes": (N,4), "keypoints": (N,17,3)} and register it in
     tools/build_detector.py alongside vitdet/yolo/yolo_pose.
   - The hand-box code itself needs NO change: _get_hand_box_from_yolo_pose at
     roughly line 3430 of sam_3d_body/models/meta_arch/sam3d_body.py is pure
     numpy keyed to COCO-17 wrist indices and touches nothing from ultralytics.
6. Eager inference first — correctness before speed. Skip TensorRT entirely for
   now; it moves the pipeline only 3.50 to 3.58 FPS and is not worth the time.
7. THE WEEK-ONE DELIVERABLE: one 10-15 second clip containing a turn, a wrist
   occlusion, and a re-entry, exported to GLB and played on a phone beside the
   original video, with raw detector overlays visible and measured runtime, peak
   VRAM, and cost per clip.

MEASURE, DO NOT TRUST: the "3.50 FPS" figure in the PRD could not be re-verified
in the upstream repo. The published 5.28 FPS uses ORACLE boxes (hand-labelled
ground truth fed in instead of a detector) and is not achievable in production.
Report your own numbers.

GATE DECISION at the end: is reconstruction usable on real phone footage, yes or
no? A clear "no" after 20 hours is a GOOD outcome, not a failure. Say so plainly
if that is the answer.

[PASTE GROUND RULES HERE]
```

---

## W5 — The 3D viewer  🟡 BLOCKED on W3's fixture

```
You are building the 3D lesson viewer for stepwise.

Repo: github.com/sreshtalluri/stepwise, branch rebuild-v4.
Read docs/DESIGN.md sections 6, 7, 7b and 10 IN FULL before writing any code.
Build against packages/motion-contract/fixtures/ — do NOT wait for the GPU
pipeline, which is being built in parallel.

STACK (pinned, peer ranges matter): three.js 0.186.0, @react-three/fiber 9.7.0
(peers react >=19 <19.3 — pin React accordingly), @react-three/drei 10.7.8,
Next.js.

DELIVER:
- Load the GLB, drive it with requestVideoFrameCallback -> mixer.setTime(mediaTime).
  The VIDEO is the clock, not a timer. 95% browser support incl. Safari 15.4+.
- Orbit, with a CONTACT SHADOW THAT MOVES as the camera orbits. This is the
  signature motion and the only affordance telling users they can rotate at all
  — no competitor has one. It also makes the body read as standing in a room.
- View presets: camera / mirror / front / back / side / top / hands / feet.
  Non-camera views carry a small "estimated view" label. Mirror is
  scale.x = -1 on the group plus CSS scaleX(-1) on the video.
- Speed 0.25-1x. Compare mode: a second angle, inset on phone, side-by-side on
  desktop, max TWO angles ever.
- The uncertainty rendering (docs/DESIGN.md §4): observed = solid; uncertain =
  desaturated with a perturbed sketchy outline; absent = not drawn, with a stub
  and a label. NOT opacity-based — opacity reads as "disabled" and fails in
  sunlight.
- A real floor plane with a visible horizon, not a wireframe grid. When
  grounding_status is "none", draw NO floor and say why.

KNOWN TRAPS:
- Hiding a bone does NOT hide its skinned surface. You need mesh-region masks.
- Missing GLB keyframes do NOT prevent interpolation across a gap. Split the
  animation into segments or explicitly block cross-gap evaluation.
- A flat single-fill figure reads as a bathroom pictogram. Two-tone shading is
  load-bearing, not decoration.

Mockups with the real tokens are in docs/design-mockups/ — open the HTML files.

[PASTE GROUND RULES HERE]
```

---

## W6 — Navigation and authoring  🟡 BLOCKED on W3's fixture

```
You are building the navigation and authoring surface for stepwise — the part
the learner actually drives.

Repo: github.com/sreshtalluri/stepwise, branch rebuild-v4.
Read docs/DESIGN.md section 7 IN FULL, plus docs/OPEN-DECISIONS.md items A4 and A5.
Build against packages/motion-contract/fixtures/.

DELIVER two-tier navigation — both scales visible at once, because a learner
asks two different questions ("where am I in the whole dance" and "where am I in
these eight counts"):

1. A slim whole-dance overview bar, always visible, with part boundaries as
   heavier ticks and the current part filled in the accent colour. Draggable.
2. The count strip: the current 8 counts, large, tabular figures. The active
   count is near-black at display weight; the others muted and smaller. WEIGHT
   AND SIZE carry the state — no highlight box, no pill, no second colour.
3. Explicit playback modes, mutually exclusive, always visible: "Play all"
   (overview bar is the scrubber) and "Loop part N" (count strip is the
   scrubber). The active one is filled so the learner always knows which.
4. Part authoring: create, rename, split, merge, delete. Drag boundaries.
5. Count anchoring: "set 1 here", half/double tempo, local re-anchor, and a
   fully manual mode for clips with no music.

RULES FROM RESEARCH:
- Loops DE-EMPHASIZE the outside rather than highlighting the inside (this is
  Soundslice's finding — it keeps the excerpt connected to its context). Fade
  outside regions toward the sunk colour with a soft gradient at both edges.
- Loop edges SNAP to count boundaries.
- NEVER bind loop creation to a swipe. Swipe always scrubs. Soundslice learned
  this the hard way on touch.
- Sections are named and semantic: "Part 2 · counts 9-16", never "0:07-0:12".
- Touch targets 88px minimum — the phone is propped three metres away.
- State is baked into the label: the button reads "0.5x", "Mirror on",
  "Loop 9-16". No icon-plus-separate-readout.

Some of A4/A5 is genuinely undesigned. Surface questions rather than inventing.

[PASTE GROUND RULES HERE]
```

---

## W7 — Marketing site, upload, processing, reveal  🟢 READY (fixture helps but not required)

```
You are building the public-facing surfaces for stepwise.

Repo: github.com/sreshtalluri/stepwise, branch rebuild-v4.
Read docs/DESIGN.md sections 7c, 7d, 7e, 7f, 11 and ESPECIALLY 7h.
Working mockups with the real design tokens are in docs/design-mockups/ —
marketing.html, screens.html. Open them.

FOUR SURFACES:

1. MARKETING SITE — loud. This is the front door and has different rules from
   the app. 60px+ display type, the accent used boldly, a dark full-bleed proof
   band, and a LIVE DEMO LESSON IN THE HERO that a stranger can drag and spin
   before signing up for anything. Three steps as an asymmetric list, never
   three equal cards. Primary action "Try it free"; "No account. Works in your
   browser." underneath.

2. UPLOAD — states the real constraints as what WORKS, not what is rejected:
   one dancer, filmed from the front, up to 60 seconds, camera held still. The
   rights line appears here once, plainly: "Only upload video you have the right
   to use."

3. PROCESSING — the job takes 2-4 minutes and the core principle is that THERE
   IS NO DEAD TIME. The learner's own clip plays IMMEDIATELY with speed, mirror
   and loop already working on it, because those are 2D operations needing no
   GPU. Below it, honest stage progress in plain language: "Found the dancer in
   every frame", "Building the body — count 9 of 32". Never "Detection complete"
   or a bare percentage. Plus "You can close this" with a copyable link, because
   it is a queue, not a session.

4. THE REVEAL — when processing completes, the camera performs ONE SLOW ORBIT
   around the figure (~2.5s, eased, front to side to front), then settles. It
   teaches the core interaction without a tooltip and is the screenshot people
   take. Once per lesson, never repeated, disabled under prefers-reduced-motion.

COPY IS THE HARD PART HERE. docs/DESIGN.md §7h documents a trap that was hit
TWICE during design by the person who wrote the rule against it: the most
exciting way to describe this product is consistently the dishonest one.
- LEGITIMATE: a dancer turning away is tracked; orbiting to see them is real.
  This is the best thing the product does. Do not undersell it.
- NOT LEGITIMATE: implying recovery of a moment that was blocked or out of frame.
Test every line: would someone who understood exactly how this works feel misled?

Banned words: elevate, seamless, unleash, next-gen, effortless, powerful.
Sentence case everywhere. No ALL-CAPS labels, no monospace, no emoji as icons.

[PASTE GROUND RULES HERE]
```

---

## W13 — The share clip generator  🟡 BLOCKED on W3 + W5

```
You are building the share-clip generator for stepwise — the thing that makes
this product spread.

Repo: github.com/sreshtalluri/stepwise, branch rebuild-v4.
Read docs/DESIGN.md sections 7g and 7h.

WHY THIS MATTERS: right now, when someone learns a dance with this app, they
have nothing to post. That is the entire growth gap. The viral object is not the
app — it is what comes out of it.

DELIVER: auto-generate a 9:16 vertical video on lesson completion.
- Top half: the original clip.
- Bottom half: the same moment on the same clock, with the 3D body slowly
  spinning.
- The active count, large, over the 3D half.
- A small "made with [name]" mark, bottom centre.
- SILENT by default — social autoplay is muted. Original audio optional.
- A few seconds long, ready to post without editing.

Evaluate BOTH approaches and recommend one with evidence: server-side render
(ffmpeg + headless three.js — more reliable, costs compute) versus client-side
canvas capture (free, but browser-dependent and can drop frames).

The honesty rules apply here too: the 3D half is labelled with its angle, and
the clip must never imply recovery of unseen motion.

[PASTE GROUND RULES HERE]
```

---

## Dependency order

```
NOW:        W3 (contract)  ·  W2 (licences)  ·  W7 (marketing/processing)
AFTER W3:   W5 (viewer)  ·  W6 (navigation)  ·  W4 (job service)
BLOCKED:    W1 (gate) — needs HF token + Modal billing
AFTER W1:   W8 real worker · W9 Kalman · W10 mesh masking · W11 beats
AFTER W5:   W13 share clip
```

W3 first, always. Four agents are waiting on its fixture.
