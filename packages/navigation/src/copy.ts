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
    summary: (total: number, perMinute: number, countOneS: string) =>
      `${total} counts, ${perMinute} a minute, count 1 at ${countOneS}.`,
    /**
     * Where the grid came from, said plainly — one of these always follows the
     * summary above.
     *
     * This used to be a single sentence ending "Nothing here was detected from
     * the music", written when beat detection was a cut-list item. Detection
     * now runs (`packages/beat-detect`, carried in `MotionResult.proposed_counts`),
     * so that sentence became false the moment a proposal could reach this
     * surface — a §7h failure pointed at the learner's counts instead of at the
     * 3D. The host passes `countsFrom` because a proposed grid and a hand-set
     * one are the same shape and this component cannot tell them apart.
     *
     * `byMusic` names the weak part rather than the strong one on purpose.
     * librosa's tracker finds beats, not downbeats — it has no notion of which
     * beat starts an eight — so the spacing is usually close and count 1 is
     * usually wrong. Saying "proposed from the music" alone would be true and
     * still misleading.
     */
    byHand: "Set by hand — nothing here came from the music.",
    byMusic:
      "Proposed from the music. Count 1 is the first beat in the clip, not necessarily the first count of the dance.",
    setOne: "Set count 1 here",
    tap: (taps: number) => `Tap the counts (${taps})`,
    tapping: (perMinute: number) => `Tapping at ${perMinute} a minute`,
    half: "Half as many counts",
    double: "Twice as many counts",
  },
} as const;
