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
| D5 | Accounts: none, magic link, or OAuth? | OPEN | Invite-only cohort needs *some* identity. Magic link is least friction. Affects A3 and A6. **New dependency from D6/D7 below:** with no accounts, anyone holding a lesson link can remove that lesson, and deduplicated uploads share one link. See "What D5 would change" under D7. |
| D6 | How long is a lesson kept? | **LEANING — recommendation below, implemented on `caching-retention`** | 180 days since the lesson was last opened. The promise on the landing mockup was untrue when written and is now true, with one copy change. |
| D7 | Can a lesson be deleted, and does the share link die with it? | **LEANING — recommendation below, implemented on `caching-retention`** | Yes and yes. The removal path is built; the link answers 410 Gone. |
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

---

## D6 — how long is a lesson kept?

**Recommendation: 180 days since the lesson was last opened. No cap on total age.**

### The honest reason, which is not the expected one

The expected argument for a retention policy is storage cost. Measured, that argument does not exist. Per solo lesson, after the changes on `caching-retention`:

| artifact | before | after |
|---|---|---|
| `{clip_id}.npz` | **61.30 MB** | **0** — deleted once the MotionResult is materialised |
| `{clip_id}.motion-result.json.gz` | — | 1.49 MB (7.15 MB of JSON, gzipped) |
| GLB, per dancer | 1.53 MB | 1.53 MB |
| source video | 1.10 MB | 1.10 MB |
| **total** | **63.93 MB** | **4.12 MB** — 15.5× smaller |

Modal charges **$0.09/GiB/month with the first 1 TiB free**. So one lesson costs **$0.00035 a month**, and 100,000 lessons fit inside the free tier. A lesson is cheaper to store for **twenty years** than to reconstruct once ($0.0839 measured, solo-01, 19.7 s, L40S). A short TTL is economically backwards: every expiry the learner then re-uploads spends two decades of storage to save nothing.

So the policy is justified on privacy, not cost, and the document should say so rather than inventing a cost pressure. The system holds video of people who never agreed to be in it (`docs/research/rights-and-privacy.md` §1). Holding it after it has stopped being useful to anyone is exposure with no upside.

### Why last-accessed, and why 180 days

Last-accessed, not upload date, because it matches how attention actually distributes: a dance people keep coming back to stays warm, and a clip uploaded once and never reopened ages out. Upload-date expiry would delete the one lesson that is working.

180 days because the number is a product judgement once cost is off the table, and the cost of being wrong is one-sided: too short and a learner loses a lesson they would have come back to; too long and we hold a stranger's video a while more. Six months covers a season away from dancing and a summer off. `docs/research/rights-and-privacy.md` §8 lists this as the builder's call — "pick a number, state it, honour it" — so it is a number, stated, and honoured by `retention.TTL_DAYS`.

**No hard ceiling on total age**, deliberately. A "delete at two years regardless" rule takes a lesson away from someone actively using it, for a privacy gain last-access expiry already delivers — the lessons that linger are the ones being opened. Add one only if the retention promise ever has to name a maximum.

### The copy, which was untrue and is the reason this was urgent

The landing mockup says **"we keep the clip while the lesson exists."** When it was written there was no deletion, expiry or retention code anywhere in the service — so the sentence was not merely vague, it was **false in both directions**: nothing was kept *because* the lesson existed, and nothing stopped being kept when it did not. That is the §7h failure pointed at users' own data rather than at the 3D.

It is now true, and needs one more clause because the lesson itself can now end:

> **We keep the clip while the lesson exists. Lessons nobody opens for six months are deleted, and a removal request deletes one straight away.**

Every clause is a promise the code keeps. Do not ship the first sentence alone: with expiry live, "while the lesson exists" reads as *indefinitely* to anyone who has not been told the lesson expires, which is the same failure in a new place. **If `TTL_DAYS` changes, this sentence changes in the same commit.**

## D7 — can a lesson be deleted, and does the share link die with it?

**Recommendation: yes and yes. Built on `caching-retention`.**

`POST /lessons/{clip_id}/removal`. The request *is* the removal — no review queue and no response-time target, because a stated target is a promise and §7h forbids promising one the code does not keep. `docs/research/rights-and-privacy.md` §6.1 ranks this the highest-value, lowest-cost mitigation available, and notes the person most likely to use it is the **dancer**, who has no copyright claim at all — so it accepts any reason, in free text, not a menu of legal categories.

**What is deleted:** the source video, every dancer's GLB, the materialised MotionResult, the npz if one survives, the export manifest, the performance record, the last-access marker, the job status, the job meta, and the content fingerprint. What remains is a tombstone holding a timestamp and a reason word — nothing derived from the person.

**The share link dies.** It answers **410 Gone**, not 404: whoever holds the link deserves to know the lesson existed and was removed rather than be told it never existed, and 410 tells caches to drop it permanently. The video and GLB endpoints refuse the same way, so nothing stays individually fetchable.

**Removal beats retention.** A removed lesson goes now, not at the next sweep, and the tombstone makes the sweeper skip it forever.

**Deduplication makes deletion genuinely better, and this is the main argument for it.** Because uploads are content-addressed, two people uploading the same clip land on one canonical lesson. A dancer asking for removal gets it removed *for everyone who uploaded it*, once — instead of having to find every scattered copy. Without dedupe, "we removed it" would be a claim about one copy dressed up as a claim about all of them.

**Two consequences, recorded rather than smoothed over:**

1. **A re-upload of removed content is reconstructed afresh.** The fingerprint is deleted with everything else, so nothing recognises the video if it comes back. Keeping the fingerprint as a blocklist would be more effective at keeping removed content off the platform — and would mean retaining a derivative of exactly the content someone asked us to delete. Deleting it is what was promised. Revisit only with a deliberate decision.
2. **A deduplicated lesson can be removed by any of its uploaders.** That is the correct behaviour for a takedown and a sharp edge for the uploader who did not ask.

### What D5 would change (not resolved here)

With no accounts, **anyone holding a lesson link can remove it**. A link is a 128-bit `uuid4`, so it is not enumerable — you have to have been given it — but an uploader's lesson can be removed by anyone they shared it with, and deduplicated uploads share one link.

Magic-link accounts would make the natural rules cheap: the uploader deletes their own outright; anyone else's request still takes it down immediately but becomes **restorable** by the uploader. That is §6.1's own suggestion and it needs D5 decided, so it is recorded here as a dependency rather than guessed at. Until then, restoring a removed lesson is a per-case email, which is the honest state.

---

## Suggested order to resolve

1. **Nothing here blocks the feasibility gate.** Start G1 (request weights) today regardless.
2. During the gate, resolve **E2** and **E3** — they are pipeline-shaped and the gate is the right place to learn them.
3. Before the viewer build: **A1, A2, A3** (the three screens that decide whether anyone uses or shares this), then **B1/B2** (the failures that will happen most), then **A4/A5** (the authoring surface).
4. **C** and **D** can be resolved as the viewer is built, except **D5** and **D8**, which affect the data model and should be decided first.
5. **A6, D9, D10** genuinely defer.
