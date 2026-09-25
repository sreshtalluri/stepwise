/**
 * The lesson's practice logic, as data. Pure: no React, no video, no three.js —
 * tested in lessonEngine.test.ts.
 *
 * One mode, nothing forced: the whole dance plays through with its counts shown until
 * the learner makes a loop — dragged across the timeline from any count or "and" to
 * any other, or a shortcut (a chip, a preset length) — with an optional build-up that
 * starts a loop at 0.5× and adds a tenth each pass. The page's one clock (the video,
 * `useVideoClock`) counts the passes; everything here is read off that count.
 *
 * Loop edges are counts or halves ("the and"). A loop {startCount, endCount} plays
 * [startCount, endCount + 1) in count coordinates, so whole-count loops mean what they
 * always did ("Counts 9–16" runs up to the next 1) and a half edge shifts the run by
 * half a count: {3.5, 6} is "3& – 6", from the and of 3 through count 6.
 */
import { partRanges } from "../../../packages/navigation/src/core";
import type { LessonStructure, LoopSpan } from "../../../packages/navigation/src/core";

export interface Eight {
  /** Stable across count-1 corrections: it names counts, not seconds. */
  id: string;
  /** 1-based, for the chip. */
  n: number;
  /** "Counts 9–16", or the learner's own part name. */
  label: string;
  startCount: number;
  /** Inclusive. */
  endCount: number;
}

export function eightsOf(structure: LessonStructure): Eight[] {
  return partRanges(structure).map((r, i) => ({
    id: `e${r.startCount}-${r.endCount}`,
    n: i + 1,
    label: /^Part \d+$/.test(r.part.name) ? spanLabel(r) : r.part.name,
    startCount: r.startCount,
    endCount: r.endCount,
  }));
}

export const sameSpan = (a: LoopSpan | null, b: LoopSpan | null) =>
  !!a && !!b && a.startCount === b.startCount && a.endCount === b.endCount;

/** How many counts a chip or a preset loops; 0 = all of it. The learner picks; 8 until they do. */
export const LOOP_ALL = 0;
export const LOOP_LENGTHS = [2, 4, 8, 16, LOOP_ALL] as const;
export const DEFAULT_LOOP_LENGTH = 8;
/** The counts a preset really is: "All" is the whole dance. */
export const presetCounts = (len: number, total: number) => (len === LOOP_ALL ? total : len);

/** Snapped to the nearest count or "and". */
export const snapHalf = (c: number) => Math.round(c * 2) / 2;
const clampCount = (c: number, total: number) => Math.max(1, Math.min(snapHalf(c), total));

/** How many counts a loop runs for (3& – 6 is 3.5). */
export const loopLength = (s: LoopSpan) => s.endCount - s.startCount + 1;

/**
 * A loop between two edges on the timeline, in count coordinates (either order; the
 * later edge is where the loop stops). Snapped to counts and "and"s unless `free`
 * (then to a hundredth of a count). Null when shorter than one count.
 */
export function edgeLoop(a: number, b: number, total: number, free = false): LoopSpan | null {
  const q = (c: number) => Math.max(1, Math.min(free ? Math.round(c * 100) / 100 : snapHalf(c), total + 1));
  const s = q(Math.min(a, b));
  const e = q(Math.max(a, b));
  return e - s >= 1 ? { startCount: s, endCount: Math.round((e - 1) * 100) / 100 } : null;
}

/** One edge moved by `delta` counts (±½ from the nudge buttons); never shorter than one count. */
export function nudgeEdge(loop: LoopSpan, edge: "start" | "end", delta: number, total: number): LoopSpan {
  if (edge === "start") return { ...loop, startCount: Math.max(1, Math.min(loop.startCount + delta, loop.endCount)) };
  return { ...loop, endCount: Math.max(loop.startCount, Math.min(loop.endCount + delta, total)) };
}

/** "3", "3&" — a count or its "and"; a free edge to a tenth. */
export const countName = (c: number) =>
  Number.isInteger(c) ? String(c) : Number.isInteger(c * 2) ? `${Math.floor(c)}&` : c.toFixed(1);

/** `len` counts from `start`, cut short at the end of the dance. */
export function loopAt(start: number, len: number, total: number): LoopSpan {
  const s = clampCount(start, total);
  return { startCount: s, endCount: Math.min(s + len - 1, total) };
}

/** The `len`-count window (counted from 1) that `count` falls in: 4s are 1–4, 5–8, 9–12… */
export const windowAt = (count: number, len: number, total: number) =>
  loopAt(Math.floor((clampCount(count, total) - 1) / len) * len + 1, len, total);

/** A count was tapped: loop `len` from it; with `anchor` (shift, or a drag) the counts between the two. */
export function countLoop(count: number, len: number, total: number, anchor: number | null = null): LoopSpan {
  if (anchor === null) return loopAt(count, len, total);
  return { startCount: clampCount(Math.min(anchor, count), total), endCount: clampCount(Math.max(anchor, count), total) };
}

/** Shift-tap on a count: the loop grows to reach it from whichever end stays put. */
export const extendAnchor = (loop: LoopSpan, count: number) => (count < loop.startCount ? loop.endCount : loop.startCount);

/**
 * Next (delta > 0) or previous (delta < 0) `len` counts from the loop — or, with the
 * whole dance playing, from the window the playhead is in. Next starts right after
 * the loop's last count, so a dragged range steps on without overlapping; delta 0
 * re-cuts the loop to `len`. Stays put at either end of the dance.
 */
export function stepLoop(loop: LoopSpan | null, hereCount: number, len: number, delta: number, total: number): LoopSpan {
  if (!loop) return windowAt(hereCount + delta * len, len, total);
  if (delta > 0) {
    const start = loop.endCount + 1 + (delta - 1) * len;
    return start > total ? loop : loopAt(start, len, total);
  }
  if (delta < 0) return loop.startCount <= 1 ? loop : loopAt(Math.max(1, loop.startCount + delta * len), len, total);
  return loopAt(loop.startCount, len, total);
}

/** The counts right after a loop, for the "Next" hint. Null at the end of the dance. */
export function nextLoop(loop: LoopSpan | null, len: number, total: number): LoopSpan | null {
  return loop && loop.endCount < total ? stepLoop(loop, 0, len, 1, total) : null;
}

/** The single chip a loop is exactly, if it is one. */
export const eightOf = (eights: readonly Eight[], loop: LoopSpan | null) => eights.find((e) => sameSpan(e, loop)) ?? null;

// ------------------------------------------------------------------ speed

/**
 * Speed, YouTube-style: four one-tap presets, and fine steps of 0.05× from 0.25× to
 * 1.25× in between. Every speed the page can play is on that grid — Build up's
 * steps (0.5, 0.6 … 1) and the phone's hold-for-half-speed included — so the value
 * shown is always exact.
 */
export const SPEED_PRESETS = [0.25, 0.5, 0.75, 1] as const;
export const SPEED_MIN = 0.25;
export const SPEED_MAX = 1.25;
export const SPEED_STEP = 0.05;
/** Snapped to the 0.05 grid and held in range; not a number is 1×. */
export const clampSpeed = (s: number) =>
  Number.isFinite(s) ? Math.round(Math.min(SPEED_MAX, Math.max(SPEED_MIN, s)) * 20) / 20 : 1; // 20 = 1 / SPEED_STEP
/** One fine step slower (−1) or faster (+1), snapped to the grid. */
export const stepSpeed = (s: number, dir: number) => clampSpeed(s + dir * SPEED_STEP);
/** S: the next preset above this speed, round to the slowest. */
export const nextPreset = (s: number) => SPEED_PRESETS.find((p) => p > s + 1e-9) ?? SPEED_PRESETS[0];
/** Every speed the page can play: what a hand-off link may carry. */
export const SPEED_GRID: readonly number[] = Array.from(
  { length: Math.round((SPEED_MAX - SPEED_MIN) / SPEED_STEP) + 1 },
  (_, i) => Math.round((SPEED_MIN + i * SPEED_STEP) * 100) / 100,
);
/** "0.65×", "1×" — exact, never rounded to a preset. */
export const speedText = (s: number) => `${Number(s.toFixed(2))}×`;

/** Build up: 0.5× on the first pass, +0.1 each pass after, held at 1×. Knobs, not physics. */
export const BUILD_FROM = 0.5;
export const BUILD_STEP = 0.1;
export function buildUpSpeed(passes: number): number {
  return Math.min(1, Math.round((BUILD_FROM + BUILD_STEP * Math.max(0, passes)) * 100) / 100);
}

/**
 * "Try another 1": the beat tracker's other candidates for count 1, each with `by`,
 * its offset in counts from count 1 as it is NOW (after any nudge or tap), wrapped
 * to the nearest eight the way `setCountOne` lands it (−4…3). Dropped: the current 1
 * and ±1, which the −1 / +1 buttons already are, and repeats. The producer's first
 * candidate stays first — it is its next best guess (packages/beat-detect
 * propose.py `_count_one`) — and the rest follow in count order, so the row reads
 * "−3, −2, +2" rather than the order the tracker happened to score them.
 */
export function oneAlternates<T extends { count_one_s: number }>(
  alts: readonly T[],
  grid: { countOneS: number; secondsPerCount: number },
): (T & { by: number })[] {
  const seen = new Set<number>();
  const out: (T & { by: number })[] = [];
  for (const a of alts) {
    const k = Math.round((a.count_one_s - grid.countOneS) / grid.secondsPerCount);
    const by = ((((k + 4) % 8) + 8) % 8) - 4;
    if (Math.abs(by) <= 1 || seen.has(by)) continue;
    seen.add(by);
    out.push({ ...a, by });
  }
  return [...out.slice(0, 1), ...out.slice(1).sort((a, b) => a.by - b.by)];
}

/** "Counts 9–16" — the coordinate is counts, never a timestamp (DESIGN.md §12.7). */
export const spanLabel = (s: LoopSpan) =>
  s.startCount === s.endCount ? `Count ${countName(s.startCount)}` : `Counts ${countName(s.startCount)}–${countName(s.endCount)}`;

/** The timeline's readout: "Loop 3& – 6". */
export const loopName = (s: LoopSpan) =>
  s.startCount === s.endCount ? `Loop count ${countName(s.startCount)}` : `Loop ${countName(s.startCount)} – ${countName(s.endCount)}`;

// ------------------------------------------------------------ done at full speed

/**
 * Which counts this browser has looped at full speed, per lesson — a true fact the
 * page shows with a quiet tick (DESIGN.md §7g: no points, no streaks). Counts, not
 * chips, so a loop of any length earns its ticks; a chip gets its tick once every
 * count in it has one. A loop with a half-count edge ticks the whole counts it plays
 * beat to beat: 3& – 6 ticks 4, 5 and 6, not 3. Same seam as lib/structure.ts: localStorage, wrapped so
 * private mode costs the ticks, never the lesson.
 */
const DONE_KEY = (lessonId: string) => `stepwise.lesson-full-speed.v2.${lessonId}`;
/** v1 stored chip ids ("e9-16"); read when there is no v2 yet, so no tick is lost. */
const DONE_KEY_V1 = (lessonId: string) => `stepwise.lesson-full-speed.v1.${lessonId}`;

/** One pass of `loop` at full speed: every count in it is done. */
export function markDone(done: ReadonlySet<number>, loop: LoopSpan): Set<number> {
  const next = new Set(done);
  for (let c = Math.ceil(loop.startCount); c <= Math.floor(loop.endCount); c++) next.add(c);
  return next;
}

export function spanDone(done: ReadonlySet<number>, s: LoopSpan): boolean {
  for (let c = Math.ceil(s.startCount); c <= Math.floor(s.endCount); c++) if (!done.has(c)) return false;
  return true;
}

export function loadDone(lessonId: string): Set<number> {
  try {
    const raw = window.localStorage.getItem(DONE_KEY(lessonId));
    if (raw) {
      const counts = JSON.parse(raw);
      return new Set(Array.isArray(counts) ? counts.filter((x): x is number => Number.isInteger(x) && x > 0) : []);
    }
    const old = JSON.parse(window.localStorage.getItem(DONE_KEY_V1(lessonId)) ?? "[]");
    let done = new Set<number>();
    for (const id of Array.isArray(old) ? old : []) {
      const m = typeof id === "string" ? /^e(\d+)-(\d+)$/.exec(id) : null;
      if (m) done = markDone(done, { startCount: Number(m[1]), endCount: Number(m[2]) });
    }
    return done;
  } catch {
    return new Set();
  }
}

export function saveDone(lessonId: string, done: ReadonlySet<number>): void {
  try {
    window.localStorage.setItem(DONE_KEY(lessonId), JSON.stringify([...done].sort((a, b) => a - b)));
  } catch {
    /* see loadDone */
  }
}

/** The loop length the learner last picked for this lesson. */
const LEN_KEY = (lessonId: string) => `stepwise.lesson-loop-length.v1.${lessonId}`;

export function loadLoopLength(lessonId: string): number {
  try {
    const raw = window.localStorage.getItem(LEN_KEY(lessonId));
    const n = raw ? Number(raw) : NaN; // Number(null) is 0, which is "All"
    return (LOOP_LENGTHS as readonly number[]).includes(n) ? n : DEFAULT_LOOP_LENGTH;
  } catch {
    return DEFAULT_LOOP_LENGTH;
  }
}

export function saveLoopLength(lessonId: string, len: number): void {
  try {
    window.localStorage.setItem(LEN_KEY(lessonId), String(len));
  } catch {
    /* private mode: kept for this visit only */
  }
}
