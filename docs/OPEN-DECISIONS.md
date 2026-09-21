# Open decisions — work through these before writing code

Everything still unresolved, grouped by kind. Decisions D1–D4 are settled and recorded in `DESIGN.md`. Nothing here is a blocker for the *feasibility gate* (which is pure pipeline work) — but all of it blocks the viewer build that follows.

Status key: **OPEN** · **LEANING** (a recommendation exists) · **DEFER** (safe to decide later, recorded so it isn't forgotten)

---

## A. Screens that do not exist yet

| # | Screen | Status | The real question |
|---|---|---|---|
| A1 | **Processing / progress** | OPEN | The job takes 2–4 minutes. What does the learner look at? A stage-by-stage list is honest but boring; a preview that fills in as it goes is better but harder. Do they have to keep the tab open? Do we email/notify when it is done? This is the screen most likely to lose people. |
| A2 | **Landing page (cold visitor)** | OPEN | Someone who has never heard of this arrives. What is the first screen? The strongest asset is a finished lesson they can touch *before* uploading anything — a live demo lesson, no signup. Needs designing as the primary conversion surface. |
| A3 | **Shared lesson (recipient view)** | OPEN | A friend opens a link. Are they a viewer-only, or can they orbit and loop? Can they upload their own from there? Is the sender's name on it? This is the growth loop and it is currently undesigned. |
| A4 | **Part editor** | OPEN | Creating, renaming, splitting, merging, and deleting parts. Drag boundaries on the overview bar? Long-press a count? This is the main thing a learner *authors*, so it deserves real design. |
| A5 | **Count anchoring ("set 1 here")** | OPEN | Detected beats will often be wrong or half/double tempo. The correction UI needs to be fast and obvious — tap on the beat, or drag the grid? What does "no music / manual counts" look like? |
| A6 | **My lessons / library** | DEFER | Does a returning user have a list? Needed once anyone has more than one lesson. Probably v1.1 but affects whether there are accounts at all. |

## B. States that are named but not designed

| # | State | Status | Note |
|---|---|---|---|
| B1 | Upload rejected — too long / wrong format / no dancer found | OPEN | Must say what to do next, not just what failed. "No dancer found" needs care — it may be the model's fault, not the video's. |
| B2 | Reconstruction partly failed | OPEN | Some counts good, some unusable. Show the lesson with gaps marked? Refuse it? This will happen often. |
| B3 | Feet cropped for most of the clip → no floor | LEANING | `DESIGN.md` says the body floats with a one-line note. Needs a drawn mockup — a floating body may look broken rather than honest. |
| B4 | Very long dance (32+ counts) | OPEN | The overview bar at 64 counts: do part ticks still read? Does the count strip page, scroll, or zoom? |
| B5 | Slow network / large upload on phone data | OPEN | Progress, resumability, and what happens if they background the app mid-upload. |
| B6 | First run — how does anyone learn they can orbit? | LEANING | The moving contact shadow is the affordance. But it needs a first-run moment — a slow auto-orbit on load, once, then stop? Needs deciding. |

## C. Interaction decisions

| # | Decision | Status | Note |
|---|---|---|---|
| C1 | Does speed change audio pitch? | LEANING | Preserve pitch (standard for practice tools). Confirm — some dancers use pitch as a cue. |
| C2 | Does the 3D have audio, or only the video panel? | OPEN | If both play, they must be sample-accurate or it is unusable. Simplest: one audio source, always the video. |
| C3 | Orbit on touch vs. scrub | OPEN | Dragging on the 3D panel could orbit *or* scrub. They conflict. Soundslice's lesson: never overload a swipe. Probably orbit on the stage, scrub only on the bars. |
| C4 | What does tapping the body do? | OPEN | Nothing? Select a limb to see its confidence? Focus the camera on it? |
| C5 | Landscape phone | OPEN | Rotating the phone is natural when propping it up. Stages side by side, controls on the right? Currently unspecified. |
| C6 | Keyboard shortcuts on desktop | LEANING | `M` `L` `S` `space` `←/→` are in `DESIGN.md`. Need a discoverable hint, and to not trap focus in the 3D canvas. |

## D. Product decisions

| # | Decision | Status | Note |
|---|---|---|---|
| D5 | Accounts: none, magic link, or OAuth? | OPEN | Invite-only cohort needs *some* identity. Magic link is least friction. Affects A3 and A6. |
| D6 | How long is a lesson kept? | OPEN | Storage cost and a privacy promise. "We keep the clip while the lesson exists" is written on the landing mockup — needs to be true and stated. |
| D7 | Can a lesson be deleted, and does the share link die with it? | OPEN | Should be yes to both; needs designing. |
| D8 | Who can upload video of whom? | OPEN | Both Meta and NVIDIA licences restrict processing people without consent. The ToS must say users only upload video they have rights to — and the upload screen should say it in plain language, once. |
| D9 | What happens when the learner wants a dance longer than 60s? | OPEN | The cap is real. Do we say "trim it" and give them a trimmer, or just refuse? |
| D10 | Public name | OPEN | `NAMES.md` has candidates. Needed before public launch, not before the gate. |

## E. Technical decisions still open

| # | Decision | Status | Note |
|---|---|---|---|
| E1 | GPU host: Modal vs RunPod | OPEN | Modal has no 4090 (L40S ~$1.95/hr) but has $30/mo free credit, scale-to-zero, and a simpler web-triggered job model. RunPod has 4090s at $0.34–1.10/hr. Decide with real numbers in G7. |
| E2 | The uncertain-limb render | OPEN | **Highest design risk.** Current attempts read as "broken" rather than "unsure". Must be prototyped against a real MHR mesh in week 1. |
| E3 | Mesh-region masking | OPEN | Hiding a bone does not hide its skinned surface. Need per-region drawable meshes or vertex masks — affects the export format, so decide before the contract freezes. |
| E4 | Accent sampling from the clip | LEANING | Nice idea, unproven. Median hue of the middle third, clamped. If it produces mud on real clips, fall back to the fixed dancer palette. Test in week 1 with the eval clips. |
| E5 | Two-environment split | SETTLED (architecture) | SAM inference on Python 3.11/Torch 2.5.1; glTF export on a separate env; arrays over the boundary. Recorded in the PRD. |
| E6 | **Reconstruction frame rate: stay at 15 fps, or go to 30?** | OPEN — **evidence now attached, decision not made** | Measured end to end on `solo-01` (`GATE-REPORT.md` § Export-quality addendum §3). What 30 fps buys *on top of* LINEAR interpolation, against a same-source-frame noise floor: the typical body joint is only **1.2 cm** better, but **wrists and striking feet are a median 3.8–4.0 cm off, p90 ~9–10 cm**, i.e. real lost accents, not noise. Cost is **$0.0839 → $0.1597 (1.90×)**, VRAM unchanged at 3.69 GB (so no bigger GPU, only more time). Recurring on a free public platform — and `caching-retention`'s dedupe changes that arithmetic, so **decide this after that branch lands, not before**. Deliberately NOT shipped as a default change. Third option nobody has priced: reconstruct at 30 fps only around high-acceleration frames (detection is already the cheap pass), which should buy most of the accent fidelity well under 1.90×. |
| E7 | **Bone direction living in the glTF translation channel** | OPEN | pymomentum puts part of some joints' bone *direction* in the translation channel rather than the parent's rotation (`l_index1`'s local offset swings 79° between adjacent keyframes at constant length). Since glTF has no "slerp the translation" mode, LINEAR lerps the chord and those bones shrink transiently between keyframes — median 0.00006 mm, p90 0.44 mm, but up to **18 mm (23% of its length) on a finger**. Exact again at every keyframe, so `bone-constraints`' CV is untouched. CUBICSPLINE is marginally worse, so this is not an argument for switching modes. The real fix is re-deriving the local decomposition at export time so bone direction lives in the rotation channel — a change to the export, not to a sampler attribute. Mostly lands on finger bones, which are already the weakest part of the reconstruction (see the `hands` branch), so the cost/benefit is genuinely unclear. |

---

## Suggested order to resolve

1. **Nothing here blocks the feasibility gate.** Start G1 (request weights) today regardless.
2. During the gate, resolve **E2** and **E3** — they are pipeline-shaped and the gate is the right place to learn them.
3. Before the viewer build: **A1, A2, A3** (the three screens that decide whether anyone uses or shares this), then **B1/B2** (the failures that will happen most), then **A4/A5** (the authoring surface).
4. **C** and **D** can be resolved as the viewer is built, except **D5** and **D8**, which affect the data model and should be decided first.
5. **A6, D9, D10** genuinely defer.
