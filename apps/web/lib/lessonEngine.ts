/**
 * The lesson's practice logic, as data. Pure: no React, no video, no three.js —
 * tested in lessonEngine.test.ts.
 *
 * One mode, nothing forced: a row of 8-count chips (from the learner's own parts,
 * one per eight until they edit them), a loop that is either one chip, a range of
 * chips, or the whole dance, and an optional build-up that starts a loop at 0.5×
 * and adds a tenth each pass. The page's one clock (the video, `useVideoClock`)
 * counts the passes; everything here is read off that count.
 */
import { partRanges } from "../../../packages/navigation/src/core";
import type { LessonStructure, LoopSpan } from "../../../packages/navigation/src/core";

export interface Eight {
  /** Stable across count-1 corrections: it names counts, not seconds. */
  id: string;
  /** 1-based, for the chip. */
  n: number;
  /** "8-count 2", or the learner's own part name. */
  label: string;
  startCount: number;
  /** Inclusive. */
  endCount: number;
}

export function eightsOf(structure: LessonStructure): Eight[] {
  return partRanges(structure).map((r, i) => ({
    id: `e${r.startCount}-${r.endCount}`,
    n: i + 1,
    label: /^Part \d+$/.test(r.part.name) ? `8-count ${i + 1}` : r.part.name,
    startCount: r.startCount,
    endCount: r.endCount,
  }));
}

export const sameSpan = (a: LoopSpan | null, b: LoopSpan | null) =>
  !!a && !!b && a.startCount === b.startCount && a.endCount === b.endCount;

/**
 * A chip was tapped. Tap = loop that eight; tap the eight already looped = play the
 * whole dance; `extend` (shift, or a drag across chips from that chip) = loop the
 * range between them. Returns the new loop, null for the whole dance.
 */
export function chipLoop(current: LoopSpan | null, chip: Eight, extend: Eight | null = null): LoopSpan | null {
  if (extend) {
    return {
      startCount: Math.min(extend.startCount, chip.startCount),
      endCount: Math.max(extend.endCount, chip.endCount),
    };
  }
  const span = { startCount: chip.startCount, endCount: chip.endCount };
  return sameSpan(current, span) ? null : span;
}

/** The eight right after a loop, for the "Next" hint. Null at the end of the dance. */
export function nextEight(eights: readonly Eight[], loop: LoopSpan | null): Eight | null {
  if (!loop) return null;
  return eights.find((e) => e.startCount > loop.endCount) ?? null;
}

/** The single eight a loop is exactly, if it is one. */
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
 * Which eights this browser has looped at full speed, per lesson — a true fact the
 * chip can show with a quiet tick (DESIGN.md §7g: no points, no streaks). Same seam as
 * lib/structure.ts: localStorage, wrapped so private mode costs the ticks, never the lesson.
 */
const DONE_KEY = (lessonId: string) => `stepwise.lesson-full-speed.v1.${lessonId}`;

export function loadDone(lessonId: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(DONE_KEY(lessonId));
    const ids = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(ids) ? ids.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

export function saveDone(lessonId: string, done: ReadonlySet<string>): void {
  try {
    window.localStorage.setItem(DONE_KEY(lessonId), JSON.stringify([...done]));
  } catch {
    /* see loadDone */
  }
}
