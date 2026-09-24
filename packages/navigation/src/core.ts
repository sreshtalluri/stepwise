/**
 * Lesson navigation core — pure, framework-free, renderer-free.
 *
 * Two kinds of data meet here:
 *
 *  1. `MotionResult.sample_times_s` — frozen contract, authoritative timeline.
 *     Length N, strictly increasing, one slot per sample even when the sample was
 *     fully suppressed. Never reconstruct a sample time as `index / fps_nominal`:
 *     frame drops, variable-rate ingest and suppression all break that arithmetic.
 *     The clip's end is `sample_times_s[N-1]`, not `source_video.duration_s`.
 *
 *  2. `LessonStructure` — counts and parts. NOT in MotionResult: the learner
 *     authors these (PRD §5, "manually set counts and named parts"). Counts are the
 *     coordinate the interface thinks in; seconds are an implementation detail
 *     (DESIGN.md §12.7).
 */

import type { MotionResult } from "../../motion-contract/src/ts/generated/motion-result";

// ---------------------------------------------------------------- timeline

/** End of the clip, per the contract: the last sample slot, not `duration_s`. */
export function timelineEndS(sampleTimesS: readonly number[]): number {
  return sampleTimesS[sampleTimesS.length - 1];
}

/**
 * The sample slot in effect at time `t`: the last index whose timestamp is <= t.
 * Binary search over the authoritative array — this is the only correct way to
 * seek, and the reason the contract insists the array exists.
 */
export function sampleIndexAt(sampleTimesS: readonly number[], t: number): number {
  let lo = 0;
  let hi = sampleTimesS.length - 1;
  if (t <= sampleTimesS[0]) return 0;
  if (t >= sampleTimesS[hi]) return hi;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1; // upper mid: converges on the last <= t
    if (sampleTimesS[mid] <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

// ---------------------------------------------------------------- structure

/** A uniform count grid. Manual by design; beat detection is a later proposal only. */
export interface CountGrid {
  /** Timeline seconds at which count 1 lands. Before 0 when the clip opens mid-eight. */
  countOneS: number;
  /** Seconds per count (one count = one beat). */
  secondsPerCount: number;
  /** How many counts the dance has. Derived from the grid and the clip length. */
  countTotal: number;
}

/** A named section of the dance. Parts partition counts 1..countTotal with no gaps. */
export interface Part {
  id: string;
  name: string;
  /** 1-based count this part begins on. The first part always begins on 1. */
  startCount: number;
}

export interface LessonStructure {
  grid: CountGrid;
  parts: Part[];
}

export interface PartRange {
  part: Part;
  index: number;
  startCount: number;
  /** Inclusive. */
  endCount: number;
}

export type PlaybackMode = "all" | "loop";

/** Inclusive count range. Loop edges are always count boundaries — never raw seconds. */
export interface LoopSpan {
  startCount: number;
  endCount: number;
}

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

export function timeOfCount(grid: CountGrid, count: number): number {
  return grid.countOneS + (count - 1) * grid.secondsPerCount;
}

/** Fractional, 1-based, unclamped — count 1.5 is halfway through count 1. */
export function countAtTime(grid: CountGrid, t: number): number {
  return (t - grid.countOneS) / grid.secondsPerCount + 1;
}

/** The whole count the playhead is inside, clamped to the dance. */
export function currentCount(grid: CountGrid, t: number): number {
  return clamp(Math.floor(countAtTime(grid, t)), 1, grid.countTotal);
}

/** Nearest count boundary to `t`, clamped to [1, countTotal + 1] (the trailing edge). */
export function nearestCountBoundary(grid: CountGrid, t: number): number {
  return clamp(Math.round(countAtTime(grid, t)), 1, grid.countTotal + 1);
}

/** Counts are displayed 1–8 within an eight, aligned to count 1 of the dance. */
export function eightStartCount(count: number): number {
  return Math.floor((count - 1) / 8) * 8 + 1;
}

export function countLabel(count: number): number {
  return ((count - 1) % 8) + 1;
}

export function partRanges(structure: LessonStructure): PartRange[] {
  const { parts, grid } = structure;
  return parts.map((part, index) => ({
    part,
    index,
    startCount: part.startCount,
    endCount: index + 1 < parts.length ? parts[index + 1].startCount - 1 : grid.countTotal,
  }));
}

export function partRangeAtCount(structure: LessonStructure, count: number): PartRange {
  const ranges = partRanges(structure);
  return ranges.find((r) => count >= r.startCount && count <= r.endCount) ?? ranges[ranges.length - 1];
}

/** "Part 2 · counts 9–16" — semantic, never "0:07–0:12" (DESIGN.md §7). */
export function partLabel(range: PartRange): string {
  return `${range.part.name} · counts ${range.startCount}–${range.endCount}`;
}

export function loopSpanForPart(range: PartRange): LoopSpan {
  return { startCount: range.startCount, endCount: range.endCount };
}

/**
 * The loop control's label states the loop it will actually play (DESIGN.md §8:
 * the state is the label). Once a handle has been dragged off a part boundary,
 * "Loop part 2" would be a lie, so the counts are named instead.
 */
export function loopLabel(structure: LessonStructure, loop: LoopSpan): string {
  const exact = partRanges(structure).find(
    (r) => r.startCount === loop.startCount && r.endCount === loop.endCount,
  );
  if (exact) return `Loop ${exact.part.name.toLowerCase()}`;
  if (loop.startCount === loop.endCount) return `Loop count ${loop.startCount}`;
  return `Loop counts ${loop.startCount}–${loop.endCount}`;
}

/** [start, end) in timeline seconds. End is the leading edge of the count after the loop. */
export function loopTimesS(grid: CountGrid, loop: LoopSpan): [number, number] {
  return [timeOfCount(grid, loop.startCount), timeOfCount(grid, loop.endCount + 1)];
}

// ---------------------------------------------------------------- invariants

/** A beat this close before 0 still counts as in the clip (a seek lands a hair early). */
const CLIP_EDGE_S = 0.02;

let nextId = 0;
const makeId = () => `part-${Date.now().toString(36)}-${(nextId++).toString(36)}`;

/**
 * Re-establish every structural invariant after an edit: counts fit the clip,
 * parts are sorted, unique, inside the dance, start at count 1, and default-named
 * parts are renumbered to their position (custom names are left alone).
 */
export function normalizeStructure(structure: LessonStructure, endS: number): LessonStructure {
  const { secondsPerCount } = structure.grid;
  // The counts run from the clip's first beat, wherever count 1 was set: a 1 set
  // mid-song is a 1 of every eight, so the beats before it count …6, 7, 8 instead
  // of being blank. Count 1 of the dance is therefore the last 1 at or before the
  // first beat in the clip, which may be before the clip starts (a pickup). Moving
  // it by whole eights only renumbers: parts shift with it and stay at the same
  // moments, and each eight added at the front gets a part of its own.
  const eights = Math.ceil(Math.floor((structure.grid.countOneS + CLIP_EDGE_S) / secondsPerCount) / 8) || 0;
  const countOneS = structure.grid.countOneS - eights * 8 * secondsPerCount;
  const countTotal = Math.max(1, Math.floor((endS - countOneS) / secondsPerCount) + 1);
  const added: Part[] = [];
  for (let e = 0; e < eights; e++) added.push({ id: makeId(), name: "Part 1", startCount: 1 + 8 * e });

  const seen = new Set<number>();
  const parts = [...added, ...structure.parts.map((p) => ({ ...p, startCount: p.startCount + 8 * eights }))]
    .sort((a, b) => a.startCount - b.startCount)
    .map((p) => ({ ...p, startCount: Math.round(p.startCount) }))
    .filter((p) => {
      if (p.startCount < 1 || p.startCount > countTotal || seen.has(p.startCount)) return false;
      seen.add(p.startCount);
      return true;
    });

  if (parts.length === 0) parts.push({ id: makeId(), name: "Part 1", startCount: 1 });
  if (parts[0].startCount !== 1) parts[0] = { ...parts[0], startCount: 1 };

  return {
    grid: { countOneS, secondsPerCount, countTotal },
    parts: parts.map((p, i) => (/^Part \d+$/.test(p.name) ? { ...p, name: `Part ${i + 1}` } : p)),
  };
}

/**
 * A starting grid so the surface has something to show before the learner sets
 * anything. It is a guess, not a detection — the UI must never present it as one
 * (OPEN-DECISIONS.md A5 is still open on how correction should feel).
 */
export function startingStructure(endS: number, secondsPerCount = 0.5): LessonStructure {
  const sized = normalizeStructure(
    { grid: { countOneS: 0, secondsPerCount, countTotal: 1 }, parts: [] },
    endS,
  );
  // One part per eight, which is how dances are actually taught.
  const parts: Part[] = [];
  for (let c = 1; c <= sized.grid.countTotal; c += 8) {
    parts.push({ id: makeId(), name: `Part ${parts.length + 1}`, startCount: c });
  }
  return normalizeStructure({ grid: sized.grid, parts }, endS);
}

// ---------------------------------------------------------------- part edits

/** Begin a new part at `count`. No-op if `count` is already a boundary. */
export function splitPartAt(structure: LessonStructure, count: number, endS: number): LessonStructure {
  const c = Math.round(count);
  if (c <= 1 || c > structure.grid.countTotal) return structure;
  if (structure.parts.some((p) => p.startCount === c)) return structure;
  return normalizeStructure(
    {
      ...structure,
      parts: [...structure.parts, { id: makeId(), name: `Part ${structure.parts.length + 1}`, startCount: c }],
    },
    endS,
  );
}

/** Absorb the following part into this one. No-op on the last part. */
export function mergePartWithNext(structure: LessonStructure, partId: string, endS: number): LessonStructure {
  const i = structure.parts.findIndex((p) => p.id === partId);
  if (i < 0 || i === structure.parts.length - 1) return structure;
  return normalizeStructure({ ...structure, parts: structure.parts.filter((_, j) => j !== i + 1) }, endS);
}

/**
 * Remove a part: its counts join the previous part (or the next one, if it was
 * first). Never deletes counts — a part is a label on a span, not the span.
 */
export function deletePart(structure: LessonStructure, partId: string, endS: number): LessonStructure {
  if (structure.parts.length < 2) return structure;
  const i = structure.parts.findIndex((p) => p.id === partId);
  if (i < 0) return structure;
  const parts = structure.parts.filter((_, j) => j !== i);
  if (i === 0) parts[0] = { ...parts[0], startCount: 1 };
  return normalizeStructure({ ...structure, parts }, endS);
}

export function renamePart(structure: LessonStructure, partId: string, name: string): LessonStructure {
  return { ...structure, parts: structure.parts.map((p) => (p.id === partId ? { ...p, name } : p)) };
}

// ---------------------------------------------------------------- grid edits

/**
 * "Set 1 here" / "Try another 1": a 1 lands on `t`, keeping the spacing, and the
 * counts fill in before it back to the clip's first beat (`normalizeStructure`).
 * Of the 1s that puts in the grid, count 1 of the dance is the one nearest the
 * current count 1, so parts move at most four counts rather than a whole eight.
 */
export function setCountOne(structure: LessonStructure, t: number, endS: number): LessonStructure {
  const eight = 8 * structure.grid.secondsPerCount;
  const one = t - eight * Math.round((t - structure.grid.countOneS) / eight);
  return normalizeStructure({ ...structure, grid: { ...structure.grid, countOneS: one } }, endS);
}

/**
 * "−1 / +1 count": move count 1 by whole counts from where it is NOW, keeping the
 * spacing — the fix for a beat tracker that found the beats but started the eight
 * on the wrong one. Presses add up, on top of a 1 set by hand as much as on the
 * proposal. Parts keep their count numbers, so every loop window moves with count 1.
 */
export function nudgeCountOne(structure: LessonStructure, deltaCounts: number, endS: number): LessonStructure {
  const { countOneS, secondsPerCount: spc } = structure.grid;
  return normalizeStructure(
    { ...structure, grid: { ...structure.grid, countOneS: countOneS + Math.round(deltaCounts) * spc } },
    endS,
  );
}

/**
 * "Tap on 1": the learner taps while the music plays, on a beat they hear as a 1.
 *
 * The tap snaps to the nearest beat of the existing grid (a tap is late by a human
 * reaction time; the tempo is not what is wrong), and that beat becomes a 1 of the
 * eight NEAREST the current count 1 — so the correction is at most four counts either
 * way and the dance is not renumbered because someone tapped in its third eight.
 * The counts before it fill in back to the start (`normalizeStructure`).
 * A tap that lands on a beat already numbered 1 changes nothing but confirms it.
 */
export function tapOnOne(structure: LessonStructure, tapS: number, endS: number): LessonStructure {
  const { countOneS, secondsPerCount: spc } = structure.grid;
  const beats = Math.round((tapS - countOneS) / spc);
  return nudgeCountOne(structure, beats - 8 * Math.round(beats / 8), endS);
}

/**
 * Half / double, re-anchored so every existing part boundary stays at the same
 * moment in time. Doubling maps count n to 2n-1; halving maps it to (n+1)/2 and
 * snaps boundaries that fall between counts onto the coarser grid.
 */
export function retempo(structure: LessonStructure, factor: "half" | "double", endS: number): LessonStructure {
  const { countOneS, secondsPerCount } = structure.grid;
  const spc = factor === "double" ? secondsPerCount / 2 : secondsPerCount * 2;
  const mapCount = (n: number) => (factor === "double" ? 2 * n - 1 : Math.round((n + 1) / 2));
  return normalizeStructure(
    {
      grid: { countOneS, secondsPerCount: spc, countTotal: 1 },
      parts: structure.parts.map((p) => ({ ...p, startCount: mapCount(p.startCount) })),
    },
    endS,
  );
}

/**
 * Tap-in: the learner taps along with the music. Count 1 is the first tap and the
 * spacing is the average gap, which is more forgiving of one bad tap than using
 * consecutive gaps. Needs two taps; returns null below that.
 */
export function gridFromTaps(
  structure: LessonStructure,
  tapsS: readonly number[],
  endS: number,
): LessonStructure | null {
  if (tapsS.length < 2) return null;
  const spc = (tapsS[tapsS.length - 1] - tapsS[0]) / (tapsS.length - 1);
  if (!(spc > 0)) return null;
  return normalizeStructure(
    { ...structure, grid: { countOneS: tapsS[0], secondsPerCount: spc, countTotal: 1 } },
    endS,
  );
}

// ---------------------------------------------------------------- playback

export interface AdvanceOptions {
  mode: PlaybackMode;
  grid: CountGrid;
  loop: LoopSpan;
  endS: number;
}

/**
 * Move the clock forward by `dtS`. "Loop part N" repeats silently (DESIGN.md §7:
 * no flash, no toast); "Play all" stops on the last count and stays there.
 */
export function advance(timeS: number, dtS: number, o: AdvanceOptions): { timeS: number; playing: boolean } {
  const next = timeS + dtS;
  if (o.mode === "loop") {
    const [a, b] = loopTimesS(o.grid, o.loop);
    const end = Math.min(b, o.endS);
    const span = end - a;
    if (!(span > 0)) return { timeS: a, playing: true };
    if (next < a) return { timeS: a, playing: true };
    if (next < end) return { timeS: next, playing: true };
    return { timeS: a + ((next - a) % span), playing: true };
  }
  if (next >= o.endS) return { timeS: o.endS, playing: false };
  return { timeS: next, playing: true };
}

// ---------------------------------------------------------------- dancers

/** DESIGN.md §3 — differ in both hue and lightness, so they survive sunlight and CVD. */
export const DANCER_COLORS = ["#F2891D", "#1E7A6F", "#C2417E", "#3F51B5"] as const;

/**
 * One accent on screen at a time (DESIGN.md §3): the selected dancer's. With a
 * single dancer that is the clip-sampled accent; with several, the fixed swatches,
 * because a sampled accent cannot tell people apart.
 */
export function accentForPerson(result: MotionResult, personIndex: number): string {
  if (result.persons.length < 2) return result.accent_color.hex;
  return DANCER_COLORS[personIndex % DANCER_COLORS.length];
}

/** Clock time as a label. Switzer with tabular figures — never monospace (DESIGN.md §5). */
export function clockLabel(t: number): string {
  const total = Math.max(0, Math.round(t));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
