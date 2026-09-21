# DESIGN.md — the dance learning platform

Design system for the video → 3D lesson product (working name `stepwise`, public name TBD in `NAMES.md`). Copy this into the rebuilt repo root; the repo's `CLAUDE.md` rule ("read DESIGN.md before any visual decision") applies to it.

Written after competitive research across STEEZY, Soundslice, Moises, Strava, Peloton, Whoop, Sportsbox AI, and the uncertainty-visualization literature. Decision D1 (visual register) was made by the builder: **practice room**.

---

## 1. The memorable thing

**A figure standing on a floor in a lit room, that you can walk around.**

Not a hologram in a void, not a skeleton on a grid, not a dashboard. Everything below serves that. If a change makes the figure feel less like a body in a room, it is the wrong change.

## 2. Visual thesis

Every dance app is a nightclub — near-black, neon accent. Every movement-tech product is a clinic — grey, charted, numeric. Nobody uses **daylight**, which is where people actually learn a dance: a studio with windows, a wooden floor, and a dark mirror on one wall.

So: a warm paper room, with the video and the 3D canvas recessed into it as darker "stages" (the mirror). The body is the only luminous thing. Chrome is quiet and physical. This also solves a real usability problem — the app is used on a phone propped across a sunlit room, where a near-black UI is genuinely harder to see.

## 3. Color

Base is warm but **greyer than cream** — deliberately avoiding the cream + terracotta combination that reads as AI-generated.

```css
--paper:        #F2EFE9;  /* the room. page background */
--paper-sunk:   #E7E1D6;  /* recessed panels, the floor, inactive tracks */
--line:         #D8D0C3;  /* hairlines, dividers, count ticks */
--stage:        #1C1917;  /* video panel + 3D canvas backdrop — the dark mirror */
--stage-deep:   #12100F;  /* 3D canvas vignette edge */
--ink:          #221E1C;  /* primary text */
--ink-muted:    #6B635C;  /* secondary text, inactive labels */
--ink-faint:    #9A9188;  /* tertiary, estimated-view labels */
```

**Accent is sampled from the clip.** On ingest, take the dominant chroma of the video (median hue of the middle third of frames, clamped to S 45–75%, L 40–60% so it always passes contrast). Every lesson looks a little different and belongs to its own dance. Persist it in `MotionResult` so the viewer and the share card agree.

Fallback and dancer colors, when sampling fails or there is more than one dancer — chosen to differ in **both hue and lightness** so they survive color-vision differences and sunlight:

```css
--dancer-1: #E8952F;  /* marigold */
--dancer-2: #1E7A6F;  /* teal */
--dancer-3: #C2417E;  /* magenta */
--dancer-4: #3F51B5;  /* indigo */
```

Rules: **one accent on screen at a time** (the current dancer's). Never a second saturated color for UI state — use weight, size, and the paper/sunk contrast instead. No purple-blue gradients, no glows, no `#000000` anywhere.

## 4. The uncertainty language

This is the part no competitor has and the part that makes the product honest. Three states, and they are **not** encoded by opacity alone (opacity fails in sunlight and reads as "disabled"):

| State | Meaning | Render |
|---|---|---|
| `observed` | The model saw this joint | Solid fill in the dancer's accent, crisp silhouette, casts contact shadow |
| `uncertain` | Occluded, blurred, or low confidence | Desaturated to grey with a **perturbed/sketchy outline** (2–3px wobble, regenerated at a low rate so it shimmers slightly), no shadow contribution. **Mockup finding: a dashed outline on a detached limb reads as "broken," not "unsure."** Keep the limb visually attached to the body and let the *surface* carry the uncertainty, not the silhouette edge |
| `absent` | Outside the frame entirely | **Not drawn.** A short stub at the last known joint plus a dotted continuation line. **Mockup finding: at phone scale a thin dotted line is invisible — it reads as dust.** The stub needs real weight (≥3px, high contrast against the stage) or a small label, and must be tested at arm's length before it counts as an honesty affordance |

The sketchy treatment is from Boukhelifa/Wood's uncertainty work, which beat blur in user studies and stays intuitive at 3–4 discrete levels. Kosara's objection to blur applies here too: if it is blurred, why show it? A limb whose pose is invented should not be drawn as a confident pose in a lighter tint.

Legend: a single persistent line under the canvas — "solid = seen · sketchy = unsure · dotted = out of frame" — in `--ink-muted`, sentence case, never a modal.

Non-front camera presets carry a small `--ink-faint` label: "estimated view". The front view carries "camera view". No badge, no icon, just the words.

## 5. Typography

Both faces are from Indian Type Foundry via Fontshare, free for commercial use — which matters for an open-source repo, and is a quiet fit for a product launching into a South Asian dance community.

- **Display / counts:** **Cabinet Grotesk** — 700/800. Slightly condensed, warm, has character without being decorative. Used for the count numerals, the lesson title, and the landing headline.
- **UI / body:** **Switzer** — 400/500/600. Neo-grotesque, extremely legible at small sizes and at distance, has **tabular figures** (essential — count numbers must not shift width as they change).
- **No monospace anywhere.** Timecode is not the coordinate people think in; counts are. If a raw timestamp must appear, set it in Switzer with tabular figures.

```css
--font-display: 'Cabinet Grotesk', 'Switzer', system-ui, sans-serif;
--font-ui:      'Switzer', system-ui, sans-serif;
```

Scale (fluid, clamped — the app is used at arm's length *and* at 3 metres):

| Role | Size | Weight | Tracking |
|---|---|---|---|
| Count numeral (active) | `clamp(2rem, 7vw, 3.5rem)` | 800 | -0.02em |
| Count numeral (inactive) | `clamp(1.25rem, 4vw, 1.75rem)` | 700 | -0.02em |
| Lesson title | `clamp(1.5rem, 3vw, 2.25rem)` | 700 | -0.02em |
| Part name | `1.125rem` | 600 | -0.01em |
| UI label | `0.9375rem` | 500 | 0 |
| Meta / legend | `0.8125rem` | 400 | 0 |

**Sentence case everywhere.** No ALL-CAPS eyebrows, no tracked-out labels, no "WORD — fragment" constructions, no middle-dot meta strings. Body copy max 65 characters.

## 6. Layout — two real compositions, not one stretched

**The product is used in two genuinely different situations, and neither is an afterthought.** Phone propped across a room while you dance. Laptop open on a desk while you study a move. Build both deliberately.

### Phone portrait (≥390px)

**Decision (D2): the two stages start equal — roughly 200px each — and either can be promoted to full height by the swap control. The choice is remembered per person.** This was deliberately *not* guessed: the video is the thing a learner already trusts (real dancer, real timing, real style) while the 3D is new and partly estimated, and there is no data yet on which one people reach for. The week-6 learning pilot answers it, and v2 sets the default from real behaviour.

```
┌───────────────────────┐
│ Say So · chorus       │
│ ┌───────────────────┐ │
│ │ ▓ 3D     ~200px ⇄ │ │
│ │     ╱│╲           │ │
│ │  ───────── floor  │ │
│ └───────────────────┘ │
│ ┌───────────────────┐ │
│ │ ▓ video  ~200px ⇄ │ │
│ └───────────────────┘ │
│ solid · sketchy · dotted
│ Part 2 · counts 9–16  │
│ 1 2 3 4 ⁵ 6 7 8       │
│ [0.5×][Mirror][Loop]  │
└───────────────────────┘
```

Transport pinned to the bottom, ≥88px targets, thumb-reachable.

### Desktop / laptop (≥1024px)

Not the phone layout widened. Landscape gives you the one thing the phone cannot: **both stages large, side by side, at the same time** — which is the actual comparison the product is for.

```
┌──────────────────────────────────────────────────────────┐
│ Say So · chorus                              [share]     │
├──────────────┬───────────────────────────┬───────────────┤
│ Parts        │  ┌─────────┐ ┌─────────┐  │ Views         │
│ ▸ Part 1     │  │ ▓ video │ │ ▓  3D   │  │ ○ camera      │
│ ▪ Part 2 ◀   │  │         │ │   ╱│╲   │  │ ○ mirror      │
│ ▸ Part 3     │  │         │ │ ──floor │  │ ○ side (est.) │
│ ▸ Part 4     │  └─────────┘ └─────────┘  │ ○ top  (est.) │
│              │  solid · sketchy · dotted │ ○ hands       │
│ + add part   │                           │ ○ feet        │
├──────────────┴───────────────────────────┴───────────────┤
│ Part 2 · counts 9–16                                     │
│  1    2    3    4    ⁵    6    7    8                    │
│  ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│  [0.5×]  [Mirror on]  [Loop 9–16]         ⌨ M L S ␣      │
└──────────────────────────────────────────────────────────┘
```

Desktop earns three things the phone cannot afford: a **persistent parts list** on the left (navigate the whole dance without scrubbing), a **persistent view switcher** on the right (all presets visible at once instead of cycling), and **visible keyboard hints** — `M` mirror, `L` loop, `S` speed, `space` play, `←/→` step a count. Max width 1400px; beyond that the stages grow, the rails do not.

### Tablet / landscape phone (768–1023px)

Stages side by side as on desktop; parts and views collapse into a single bottom sheet. Do not show three rails at this width.

### What stays identical across all three

The count strip is always full width and always the primary navigation. Transport labels always carry their state. The uncertainty legend is always visible under the 3D stage. Nothing is hover-only — everything must work by touch.

## 7. Navigation — two scales, always both visible (D3)

A learner asks two different questions, and the design answers both at once rather than making one hide the other.

**Tier 1 — the overview bar.** A slim full-width bar for the whole dance, always visible. Part boundaries are heavier ticks; the current part is filled in the accent. Drag it anywhere. Total length labelled at both ends. This is what makes "just play the whole thing" an obvious, first-class action instead of something you assemble out of parts.

**Tier 2 — the count strip.** The current eight counts, large. Tabular numerals; the active count is `--ink` at display weight and the rest are `--ink-muted` and smaller. **Weight and size carry the state — no highlight box, no pill, no second colour.** A hairline tick under each count; the position is a single filled accent dot sliding along.

**Playback mode is explicit, not inferred.** Two controls, always visible, mutually exclusive: `▶ Play all` runs the dance start to finish, the overview bar being the primary scrubber. `↺ Loop part 2` repeats the current part, the count strip being the primary scrubber. The learner always knows which one they are in because the active one is filled.

- Sections are named and semantic — "Part 2 · counts 9–16", never "0:07–0:12".
- **Loop de-emphasizes the outside, it does not highlight the inside** (Soundslice's finding): counts and overview regions outside the active loop fade toward `--paper-sunk` with a soft gradient at both edges, so the excerpt stays connected to its context. Loop edges snap to count boundaries.
- Loop is never created by a swipe — swipe always scrubs. Dedicated loop control, then drag the two handles.
- At the end of a looped part: repeat silently, no flash, no toast. At the end of "play all": stop on the last count and offer "play again" and "loop the last part".

```
┌──────────────────────────────┐
│ whole dance  0:00 ─────  0:14│
│ ▏━━━┃━━●━━┃━━━━┃━━━━━━━━━━━━│
│  p1   p2    p3   p4          │
├──────────────────────────────┤
│ Part 2 · counts 9–16         │
│  1  2  3  4  ⁵  6  7  8      │
│  ── ── ── ── ─● ── ── ──     │
├──────────────────────────────┤
│ [▶ Play all]  [↺ Loop part 2]│
└──────────────────────────────┘
```

## 7a2. Choosing a dancer (MVP)

Multiple dancers are reconstructed and rendered in the MVP (see `docs/PRD.md`).
The learner picks whose body they are learning from.

- **Default:** the dancer nearest the frame centre with the highest coverage and
  confidence. Usually the one the camera framed deliberately.
- **Switching:** one tap. The lesson re-anchors to that person's body; counts and
  parts are unchanged, because they belong to the dance rather than the dancer.
- **Colour:** each dancer gets one of the four dancer colours, which differ in
  both hue and lightness so they survive colour-vision differences and sunlight.
  Only the *selected* dancer is saturated; the others render in a muted neutral
  so the screen never has two competing accents.
- **On phone:** a compact row of dancer chips above the count strip, not a
  dropdown — one tap, not two.
- **At a crossing:** if track confidence collapses where dancers overlap, mark
  that span uncertain on both. **Never silently swap identities** — a confident
  wrong body is the worst failure this product can produce.

Not in the MVP, and deliberately so: cross-dancer consensus, the sync check, the
formation view, and "which one is me". Those are v2 (§ v2 in the PRD) and are
the expensive logic — the reconstruction itself is nearly free.

## 7b. Compare mode — two angles at once (D4)

**Off by default**, so the simple case stays simple. Turning it on shows a second angle alongside the first, both driven by the same clock:

- **Phone:** the second angle appears as an inset panel over the main view (bottom-right, ~38% width), tap to swap which is primary, drag to reposition if it covers the body.
- **Desktop ≥1024px:** the second angle takes an equal side-by-side panel.
- **Tablet:** inset, as phone.

Why it exists: the moment a learner needs help is a turn (wants front + side) or footwork (wants body + feet). One-at-a-time forces them to hold the missing angle in their head — the exact mental rotation this product exists to remove.

Rules: maximum two 3D angles at once, ever — three panels means none of them are readable. Each panel keeps its own "camera view" / "estimated view" label. The uncertainty legend applies to both and is not duplicated.

## 7c. Processing — make the wait usable (A1)

The job takes 2–4 minutes. The design principle: **there is no dead time, because the video is already useful.**

- The learner's own clip **plays immediately** in the stage, with speed, mirror, and loop already working on it. Those are 2D operations that need no GPU. A learner can begin working on the dance the second they upload.
- Below it, honest stage-by-stage progress in **plain language**: "Found the dancer in every frame", "Building the body — count 9 of 32", "Working out the floor", "Finding the counts". Never "Detection complete" or a bare percentage. The count-based progress is meaningful to a dancer in a way a percentage is not.
- **"You can close this."** A copyable link, and the job survives. This removes the single biggest anxiety of a long wait and is honest about it being a queue, not a session.
- Rough time remaining, stated loosely ("about 2 minutes left") — never a false-precision countdown.
- When it finishes: the 3D fades in beside the video. No modal, no confetti, no sound.

Open: whether to progressively render the partial body as it builds. Compelling, but a half-built body may read as a broken one. Prototype in week 1 before committing.

## 7d. Landing — let them touch a lesson first (A2)

The strongest asset is a **finished lesson a stranger can use before uploading anything**. So the hero is not a screenshot or a headline over a video — it is a live, working lesson with the view chips (front / side / top / mirror) already tappable.

- **No account needed to try.** Stated plainly under the primary action.
- The primary action is "Add your own clip" — specific, not "Get started".
- "Works best with" states the real constraints in plain sentences: filmed from the front on one camera held still, up to 60 seconds, no cuts between shots. One dancer or several — the learner picks whose body they learn from (§7a2). Framed as *what works*, not as *what we reject*. **Corrected 2026-09-18:** this line used to say "one dancer" as a hard constraint; PRD §5 "Multi-dancer, revised 2026-09-18" removed that cap.
- The rights line sits here, once, in plain language: "Only upload video you have the right to use." Followed by the sentence D8's research found missing, which names the person most likely to need it: **"Anyone in a clip can ask us to take it down, and we will."**
- The retention line sits here too, once (D6):

  > **We keep the clip while the lesson exists. Lessons nobody opens for six months are deleted, and a removal request deletes one straight away.**

  **This line replaces "we keep the clip while the lesson exists", which was on this mockup before any deletion code existed and was therefore false in both directions** — nothing was kept *because* a lesson existed, and nothing stopped being kept when one did not. See §7h below: the honesty rule is not only about the 3D. If the retention period changes, this sentence changes in the same commit, or the product is lying about the learner's own data.
- Below the fold: one real before/after (a move that is unclear in the video, clear in 3D) — the single most persuasive thing available, and it must be a real clip, not a mock.

**Copy violation caught in review:** the first draft of this screen said *"Every angle, even ones the camera never shot."* That is precisely the overclaim §1 of the PRD bans — a monocular model produces a *plausible* pose for what it could not see, not the truth. Corrected to **"Every angle, from the one video you have."** This is a standing trap: the exciting way to describe the product is the dishonest way, and it will keep resurfacing in marketing copy. Any copy implying recovery of unseen motion is a bug.

## 7e. Two front doors — marketing site vs. app

They have different jobs and different rules, and conflating them is why the first landing draft felt flat.

**Marketing site** (`/`) — loud. Big display type at 60px+, the accent used boldly, a dark full-bleed proof band for contrast, and a **live demo lesson in the hero that a stranger can drag and spin before signing up for anything**. Sections: hero with demo → proof band (one real before/after) → three steps as an asymmetric list, never three equal cards → closing call to action. Primary action is "Try it free"; "No account. Works in your browser." sits underneath.

**The app** (`/lesson/...`) — calm. Everything in §6–§7d. The learner is here for forty minutes repeating an 8-count; energy here is fatigue.

The rule: **loudness is allowed at the front door and forbidden in the room.**

## 7f. The reveal — make the first 3D moment land

When processing completes, the 3D does not simply appear. The camera performs **one slow orbit** around the figure (about 2.5 seconds, eased, front → side → front), then settles at the camera view.

It does three jobs at once: it teaches the core interaction without a tooltip, it is the screenshot people take, and it is the moment the product proves what it is. It fires **once per lesson, never again** — and never on a shared-link open in reduced-motion mode. No modal, no confetti, no sound.

## 7g. The share clip — the actual viral object

**The most important thing for reach, and it was missing from the plan entirely.** When someone learns a dance here, they currently have nothing to post. This fixes that.

On lesson completion, auto-generate a **9:16 vertical video**, a few seconds long, ready to post:
- Top half: the original clip.
- Bottom half: the same moment, same clock, with the 3D body spinning slowly.
- The active count, large, over the 3D half.
- A small mark bottom-centre: "made with [name]".
- Silent by default (social autoplay is muted); the original audio optional.

Why this and not badges: it is inherently a TikTok, it is a thing nobody else can produce, it carries the entire pitch in five seconds with no words, and it is posted *by the learner* into exactly the audience that wants it. The honesty rules apply here too — the 3D half is labelled with its angle, and the clip never implies recovery of unseen motion.

**Gamification, deliberately limited.** Show "3 of 8 parts" — a true and useful fact about learning a dance. Do **not** add points, XP, streaks, badges, or levels. The motivation to learn a dance you chose is already intrinsic; decorating it with invented scores makes a calm tool tiring and reads as slop.

## 7h. What the product may and may not claim

Refined after a correction in review — the earlier version of this section was itself imprecise. There are **three** distinct situations, not two, and they have different honesty rules.

| Situation | Can the model see the body? | Claim allowed? |
|---|---|---|
| **1. The dancer turns away, fully visible from behind** | **Yes** — a body is visible, just from another side. Rotation is tracked through the turn. | **Yes, and this is the product's best claim.** In the flat video you cannot see what their arms are doing when their back is turned; in 3D you can orbit and look, because the body was tracked. |
| **2. Something blocks the body** — another dancer, a prop, a limb hidden behind the torso | **No pixels** for that part. Filled in from what a human body can plausibly do. | **No.** Mark it `uncertain` and render it as such. Never claim to show what was blocked. |
| **3. Out of frame, or the camera cuts away** | **Nothing.** | **No.** `absent`. Not drawn. |

**Case 1 is the whole product and must not be undersold.** An earlier draft of this document wrongly lumped "the dancer turns away" in with occlusion, which would have thrown away the most useful and most honest thing the system does.

**The nuance inside case 1:** facing away is *lower* confidence, not zero. Depth ambiguity worsens — from behind it is harder to tell whether an arm reaches forward or back, since both project to similar silhouettes (the same family as the left/right flip problem). And a dancer's hands in front of their chest are occluded by their own torso, so overall orientation and limb position are tracked well while fine hand detail is estimated. Back-facing frames should therefore skew toward `uncertain`, not `absent`, and the render must show that.

### The same rule, pointed at their data

Everything above is about claims on the **motion**. The identical rule applies to claims about **what we keep, for how long, and who can make it stop** — and that is where this document had already broken it.

"We keep the clip while the lesson exists" sat on the landing mockup while the service contained no deletion, expiry or retention code of any kind. Nobody wrote it as a lie; it was written as an *intention* and read as a *guarantee*, which is exactly how the overclaim about unseen motion gets written too. A false promise about someone's video is worse than a false promise about a shoulder angle, because the person it misleads may not be the person who uploaded it.

The rule, stated so it is checkable in review:

- **Never state a retention period, a deletion behaviour, or a removal promise that the code does not implement.** If the deletion path does not exist, the line does not ship. `docs/research/rights-and-privacy.md` §7c puts it the same way: a false retention promise is worse than no retention promise.
- **A retention number in copy and the constant in the code change in the same commit.** They are one fact written twice.
- **Describe the mechanism, not a guarantee.** "Anyone in a clip can ask us to take it down, and we will" names what happens. "Your data is secure" and "we protect your privacy" name nothing and are banned here for the same reason "seamless" is banned in §11.
- Copy may not say **"we check"**, **"we verify"**, or **"we have permission"**. We do none of those things.

The §7h test is unchanged, only re-aimed: *would someone who understood exactly how this works feel misled?*

**Where the removal link lives.** On the lesson page, at the bottom, a quiet plain-text link — not a button, not in the control bar. It reads **"Ask us to remove this lesson"**. It has to be findable by someone who arrived from a shared link and recognised themselves in the video, and invisible to someone practising. The 88px touch target of §8 does not apply: this is not a control, and making it thumb-sized on a phone propped on the floor would put it in the way of the thing the page is for. Its confirmation states what actually happened, in the voice of §11 — **"Removed. The video, the 3D and the link are gone."** — and never "we're sorry to see you go".

### The copy trap

The banned overclaim was written **twice during this design pass**, in two different screens, by the person who wrote the rule:

1. "Every angle, even ones the camera never shot." → "Every angle, from the one video you have."
2. "When the dancer turns away, or someone blocks the shot, you lose the step." → "A phone films one angle. The step you need is often side-on or from above."

That is gravity, not carelessness. But note the second correction was itself imprecise in the opposite direction — over-cautious about case 1. **Both failure modes are real: overclaiming case 2/3, and underclaiming case 1.**

The test for any line of copy: *would someone who understood exactly how this works feel misled?* Promising a synthesised **viewpoint** of a body the model tracked is honest. Promising a recovered **moment** the model never saw is not.

## 8. Controls

State is baked into the label, following STEEZY: the button reads `0.5×`, `Mirror on`, `Loop 9–16` — not an icon with a separate readout somewhere else. One glance from across the room tells you the state.

Touch targets **88px minimum** (2× the iOS 44pt guideline) because the phone is on the floor three metres away. Keyboard: `M` mirror, `L` loop, `S` speed cycle, `space` play/pause, `←/→` step one count, arrow+shift step one part.

Tactile feedback on `:active` — `scale(0.98)` and `translateY(1px)`. No ripples, no glows.

## 9. Motion

`MOTION_INTENSITY: 3` — this is a tool people stare at for forty minutes, not a landing page. Almost nothing moves on its own.

**The one exception, and it is the signature:** the **contact shadow under the figure swings as you orbit**. No competitor exposes any affordance for "you can rotate this" (Sportsbox has none at all). A shadow that moves with the camera is a self-explaining depth cue that teaches the interaction without a tooltip. It is also the thing that makes the body read as standing in a room rather than floating in space.

Everything else: `transition: 160ms cubic-bezier(0.16, 1, 0.3, 1)` on hover and state changes. Respect `prefers-reduced-motion` — the shadow still moves (it is information, not decoration), the transitions stop.

## 10. The 3D stage

- Background `--stage`, with a subtle radial vignette toward `--stage-deep` at the edges.
- **A real floor plane**, not a wireframe grid: a matte surface a few shades above `--stage`, with a visible horizon line and a soft contact shadow under the figure. **Mockup finding: a 1px floor line is not a floor.** The horizon needs to be unmistakable — the entire premise is a body standing in a room. A faint grid may appear on the floor at low opacity for spatial reference, but the floor is a surface first.
- When grounding fails (feet cropped for most of the clip): **no floor at all**, and the figure floats against the vignette with a one-line note, "no floor — feet not visible." Never fake a plane.
- Toon material, two-tone. The accent is the mid-tone; the shadow side is the accent at 70% lightness. No specular, no rim light, no fresnel.
- **Mockup finding: a flat single-fill figure reads as a bathroom pictogram, not a dancer.** The two-tone break is not optional decoration — it is what makes the form legible as a body. Verify against a real MHR mesh at LOD 3–4 in week 1, and if it still reads as signage, add a third tone or a subtle ambient-occlusion bake at the joints.
- Camera: orbit constrained to a band (no pole flipping), gentle damping, double-tap to return to camera view.

## 11. Writing

Plain, active, sentence case. The interface's voice, not a person's.

- "Upload a clip" not "Get started"
- "Feet not visible in this clip" not "Warning: incomplete data"
- "This angle is estimated" not "⚠️ ESTIMATED VIEW"
- Empty upload screen states what works: "Filmed from the front, on one camera held still. Up to 60 seconds, with no cuts between shots. One dancer or several — you pick whose body you learn from." (Corrected 2026-09-18 — see §7d.)
- Errors say what happened and what to do, and never apologize.
- Banned: elevate, seamless, unleash, next-gen, effortless, powerful, revolutionize. No exclamation marks. No emoji as icons — SVG only (Phosphor, `weight="regular"`, one weight everywhere).

## 12. What this system forbids

Collected so they are checkable in review:

1. Near-black page background with a single neon/cyan accent (the previous version, and the AI default).
2. ALL-CAPS tracked-out eyebrow labels.
3. Monospace for timestamps or data.
4. Opacity-only encoding of uncertainty.
5. A wireframe grid standing in for a floor.
6. Any second saturated UI color alongside the dancer accent.
7. Timestamps as the primary coordinate instead of counts.
8. Highlighting the inside of a loop instead of dimming the outside.
9. Swipe-to-create-loop on touch.
10. Numbered `01 / 02 / 03` markers, decorative blobs, gradient washes, generic 3-column card rows.
11. Drawing a limb the model did not see as a confident pose in a lighter tint.
12. Any statement about retention, deletion or removal that the code does not implement — including a retention period in copy that no constant in the code matches (§7h).
13. "Secure", "protected", "private by design", "we verify", "we check" — guarantees with no mechanism behind them.


---

## 13. Review log — plan-design-review, 2026-09-17

Reviewed against the PRD before any code exists. Mockups built as real HTML with the actual tokens (`~/.gstack/projects/Projects_PRDs/designs/lesson-viewer-20260917/`): `viewer.html` (phone) and `desktop.html`.

**Initial rating 7/10**, unusually high for a pre-build plan because the system already named real hex values, real typefaces, a signature motion, and a banned-patterns list.

**What the mockups proved works:** the practice-room register is unmistakable and is neither nightclub nor clinic. The count strip is legible as primary navigation and the active numeral reads from across a room. State-in-label transport ("Mirror on / tap to turn off") beats icon-plus-readout. The desktop parts rail and views rail earn their space.

**What the mockups disproved or exposed:**
1. A flat single-fill figure reads as a **bathroom pictogram**. Two-tone shading fixed it on desktop and is therefore load-bearing, not decoration.
2. A 1px floor line **is not a floor**. The horizon needs real weight.
3. A bare dotted stub for an absent limb **is invisible at phone scale** and needs an accompanying label ("foot not in frame").
4. A dashed outline on a limb reads as **broken, not uncertain** — and still reads as a detached grey object. Unresolved: the uncertainty must live in the *surface*, not the silhouette edge, and must stay visually attached to the body. **This is the highest-risk open design problem** and should be prototyped against a real MHR mesh in week 1.
5. Any label drawn near the canvas edge **clips**. Keep annotations inside a safe inset.

**Open at end of review:** #4 above. Everything else is specified.

**Decisions taken:** D1 practice-room register. D2 phone stages start equal with swap-to-promote, remembered per person — deliberately not guessed, because the week-6 learning pilot is the honest way to answer it.

**Still unverified:** every font and colour choice here has been seen only in a static mockup. None has been tested on a phone at three metres in daylight, which is the actual use case. Do that in week 1.
