/**
 * Every user-facing string on the navigation and authoring surface.
 *
 * Shaped to match `apps/web/lib/copy.ts` (W7) so the DESIGN.md §11 copy lint in
 * `apps/web/test/copy.test.ts` can sweep it too. To wire it up, add one line
 * there:
 *
 *     export { copy as navigation } from "@stepwise/navigation";
 *
 * Rules that apply to every line here: sentence case, plain and active, the
 * state is in the label (DESIGN.md §8) and the coordinate is counts, never a
 * timestamp (§12.7). Nothing on this surface makes a claim about what the model
 * saw, so §7h does not bite here — keep it that way.
 */

export const copy = {
  overview: {
    /** Left of the whole-dance bar. The clock times beside it are secondary. */
    wholeDance: "whole dance",
  },

  dancers: {
    groupLabel: "Dancer",
    chip: (n: number) => `Dancer ${n}`,
  },

  parts: {
    railLabel: "Parts",
    startHere: (count: number) => `Start a new part on count ${count}`,
    joinNext: (name: string) => `Join ${name} to the next part`,
    remove: (name: string) => `Remove ${name}`,
    nameField: "Name",
  },

  transport: {
    modeGroupLabel: "Playback mode",
    play: "Play",
    pause: "Pause",
    playAll: "Play all",
    loopStartHandle: (count: number) => `Loop starts at count ${count}`,
    loopEndHandle: (count: number) => `Loop ends after count ${count}`,
    keys: "L loop · space play · ←/→ step a count · shift ←/→ step a part",
  },

  counts: {
    editor: "Counts and parts",
    /**
     * Two variants, because since 2026-09-20 there are two ways a grid can get
     * here and saying the wrong one is a lie either way. The old single line
     * ("Nothing here was detected from the music") was written when detection
     * did not exist; once `MotionResult.beat_proposal` started seeding the
     * grid it became false, and false in the direction DESIGN.md §7h cares
     * about least forgivingly — a statement of fact about where a number came
     * from. `isStillProposed()` in core.ts decides which line applies.
     */
    summary: (total: number, perMinute: number, countOneS: string) =>
      `${total} counts, ${perMinute} a minute, count 1 at ${countOneS}. Set these by hand. Nothing here was detected from the music.`,
    /** Same facts, but the grid is still the machine's guess, not the learner's. */
    summaryProposed: (total: number, perMinute: number, countOneS: string) =>
      `${total} counts, ${perMinute} a minute, count 1 at ${countOneS}. Proposed from the music — change anything here and it becomes yours.`,
    setOne: "Set count 1 here",
    tap: (taps: number) => `Tap the counts (${taps})`,
    tapping: (perMinute: number) => `Tapping at ${perMinute} a minute`,
    half: "Half as many counts",
    double: "Twice as many counts",
  },
} as const;
