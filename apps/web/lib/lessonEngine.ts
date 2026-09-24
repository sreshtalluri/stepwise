/**
 * The lesson's practice logic, as data. Pure: no React, no video, no three.js —
 * tested in lessonEngine.test.ts.
 *
 * One mode, nothing forced: a row of chips (the learner's own parts, one per eight
 * until they edit them) to find your way, and a loop of any run of counts — 2, 4 or 8
 * from a chip or a count, a range dragged across either, or the whole dance — with an
 * optional build-up that starts a loop at 0.5× and adds a tenth each pass. The page's
 * one clock (the video, `useVideoClock`) counts the passes; everything here is read
 * off that count.
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

/** How many counts a tap loops. The learner picks; 8 until they do. */
export const LOOP_LENGTHS = [2, 4, 8] as const;
export const DEFAULT_LOOP_LENGTH = 8;

const clampCount = (c: number, total: number) => Math.max(1, Math.min(Math.round(c), total));

/** `len` counts from `start`, cut short at the end of the dance. */
export function loopAt(start: number, len: number, total: number): LoopSpan {
  const s = clampCount(start, total);
  return { startCount: s, endCount: Math.min(s + len - 1, total) };
}

/** The `len`-count window (counted from 1) that `count` falls in: 4s are 1–4, 5–8, 9–12… */
export const windowAt = (count: number, len: number, total: number) =>
  loopAt(Math.floor((clampCount(count, total) - 1) / len) * len + 1, len, total);

/**
 * A chip was tapped. Tap = loop `len` counts from its start; tap it again while that
 * is the loop = play the whole dance; `extend` (shift, or a drag across chips from
 * that chip) = loop the whole chips between them. Returns the new loop, null for the
 * whole dance.
 */
export function chipLoop(current: LoopSpan | null, chip: Eight, len: number, total: number, extend: Eight | null = null): LoopSpan | null {
  if (extend) {
    return {
      startCount: Math.min(extend.startCount, chip.startCount),
      endCount: Math.max(extend.endCount, chip.endCount),
    };
  }
  const span = loopAt(chip.startCount, len, total);
  return sameSpan(current, span) ? null : span;
}

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
  if (delta < 0) return loop.startCount === 1 ? loop : loopAt(Math.max(1, loop.startCount + delta * len), len, total);
  return loopAt(loop.startCount, len, total);
}

/** The counts right after a loop, for the "Next" hint. Null at the end of the dance. */
export function nextLoop(loop: LoopSpan | null, len: number, total: number): LoopSpan | null {
  return loop && loop.endCount < total ? stepLoop(loop, 0, len, 1, total) : null;
}

/** The single chip a loop is exactly, if it is one. */
export const eightOf = (eights: readonly Eight[], loop: LoopSpan | null) => eights.find((e) => sameSpan(e, loop)) ?? null;

/** Build up: 0.5× on the first pass, +0.1 each pass after, held at 1×. Knobs, not physics. */
export const BUILD_FROM = 0.5;
export const BUILD_STEP = 0.1;
export function buildUpSpeed(passes: number): number {
  return Math.min(1, Math.round((BUILD_FROM + BUILD_STEP * Math.max(0, passes)) * 100) / 100);
}

/** "Counts 9–16" — the coordinate is counts, never a timestamp (DESIGN.md §12.7). */
export const spanLabel = (s: LoopSpan) => (s.startCount === s.endCount ? `Count ${s.startCount}` : `Counts ${s.startCount}–${s.endCount}`);

// ------------------------------------------------------------ done at full speed

/**
 * Which counts this browser has looped at full speed, per lesson — a true fact the
 * page shows with a quiet tick (DESIGN.md §7g: no points, no streaks). Counts, not
 * chips, so a loop of any length earns its ticks; a chip gets its tick once every
 * count in it has one. Same seam as lib/structure.ts: localStorage, wrapped so
 * private mode costs the ticks, never the lesson.
 */
const DONE_KEY = (lessonId: string) => `stepwise.lesson-full-speed.v2.${lessonId}`;
/** v1 stored chip ids ("e9-16"); read when there is no v2 yet, so no tick is lost. */
const DONE_KEY_V1 = (lessonId: string) => `stepwise.lesson-full-speed.v1.${lessonId}`;

/** One pass of `loop` at full speed: every count in it is done. */
export function markDone(done: ReadonlySet<number>, loop: LoopSpan): Set<number> {
  const next = new Set(done);
  for (let c = loop.startCount; c <= loop.endCount; c++) next.add(c);
  return next;
}

export function spanDone(done: ReadonlySet<number>, s: LoopSpan): boolean {
  for (let c = s.startCount; c <= s.endCount; c++) if (!done.has(c)) return false;
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
    const n = Number(window.localStorage.getItem(LEN_KEY(lessonId)));
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
