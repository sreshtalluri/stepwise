# @stepwise/navigation

The lesson navigation and authoring surface: two scales of navigation always both
visible (`docs/DESIGN.md` §7), plus the controls that let a learner set counts and
name parts (PRD §5).

Renderer-free on purpose. Nothing here imports three.js, a video element, or
anything from the viewer, so W5's 3D work and this surface stay separable.

## What is in it

| | |
|---|---|
| `src/core.ts` | Pure timeline and structure logic. No React. This is where the tests are. |
| `src/LessonNavigator.tsx` | `<LessonNavigator>` (both tiers, modes, transport, editor) and `<PartsRail>` (the persistent desktop left rail). |
| `src/copy.ts` | Every user-facing string, shaped for the DESIGN.md §11 copy lint. |
| `src/navigation.css` | Styling. Declares no design tokens — see below. |
| `demo/` | A harness showing the phone and desktop compositions side by side. `npm run demo`. |

## Using it

Fully controlled: the host owns the clock, the structure, the mode and the
selection, and passes them down. `advance()` is exported so the host's clock gets
the looping and end-of-dance behaviour for free.

```tsx
import { LessonNavigator, PartsRail, advance, startingStructure } from "@stepwise/navigation";
import "@stepwise/navigation/navigation.css";
```

Phone: render `<LessonNavigator>` under the stages. Desktop: `<PartsRail>` in the
left rail and `<LessonNavigator>` across the foot (`docs/DESIGN.md` §6). Breakpoints
are container queries, so the surface responds to its own width, not the window's.

Anything the viewer owns — speed, mirror, view presets — goes in as `children` and
lands in the transport row.

## Two integration notes

**Design tokens.** This package declares none. `apps/web/app/globals.css` is the
single declaration site; the demo harness carries its own copy. Transitions use
`--t` with the DESIGN.md §9 value inlined as a fallback.

**Copy lint.** Add one line to `apps/web/lib/copy.ts` and the §11 lint covers this
surface too:

```ts
export { copy as navigation } from "@stepwise/navigation";
```

## The timeline rule

`MotionResult.sample_times_s` is authoritative: length N, strictly increasing, one
slot per sample even when the sample was suppressed. `sampleIndexAt()` binary
searches it. Nothing in this package ever computes a sample time as
`index / fps_nominal`, and the clip's end is `sample_times_s[N-1]`, not
`source_video.duration_s` — the two differ in `good-lesson.json` and there is a
test pinning that.

Counts and parts are **not** in `MotionResult`. They are authored by the learner and
live in `LessonStructure`, which the host persists.

## What is deliberately not decided here

`OPEN-DECISIONS.md` A4 (part editor) and A5 (count anchoring) are open, so nothing
gestural was invented: every edit is a labelled button acting on the playhead. See
the questions raised in the W6 report before designing the real interactions.
