/**
 * The lesson path, as data. Pure: no React, no video, no three.js — tested in
 * lessonEngine.test.ts.
 *
 * A lesson is a list of UNITS (each 8-count, plus "Together 1 to N" joins after
 * every second one — the progressive-part method), and every unit is drilled as a
 * flat SCHEDULE of ROUNDS, one round per loop of the unit:
 *
 *   Watch 1×  →  Slow 0.5× ×3  →  Build up 0.5, 0.6 … 1×, then Your turn  →  Full speed
 *
 * then "Got it". The page's one clock (the video, `useVideoClock`) calls
 * `nextRound` each time it wraps the loop; everything the learner sees — speed,
 * which step is lit, whether the dancer is dimmed — is read off the round index.
 * There is no second timer to drift.
 *
 * Units come from the learner's own `LessonStructure` parts (one per eight until
 * they edit them), so a count-1 correction moves every loop window with it.
 */
import { partRanges } from "../../../packages/navigation/src/core";
import type { LessonStructure } from "../../../packages/navigation/src/core";

export type Step = "watch" | "slow" | "build" | "full";
export const STEPS: readonly Step[] = ["watch", "slow", "build", "full"];

export interface Round {
  step: Step;
  speed: number;
  /** Video and mesh dimmed, music and counts keep going: the learner does it alone. */
  yourTurn?: boolean;
}

/** Calibration knobs, not physics. STEEZY's own advice is ~5 loops at half speed. */
export const SLOW_LOOPS = 3;
export const FULL_LOOPS = 2;

/** 0.5 → 1 in +0.1 steps, rounded so 0.1 arithmetic never shows as 0.7000000001×. */
export function rampSpeeds(from = 0.5, to = 1, by = 0.1): number[] {
  const out: number[] = [];
  for (let x = from; x < to - 1e-9; x += by) out.push(Math.round(x * 100) / 100);
  out.push(to);
  return out;
}

export interface Unit {
  /** Stable across count-1 corrections: it names counts, not seconds. */
  id: string;
  kind: "eight" | "join";
  label: string;
  /** For the phone path dots: "3", "1–4". */
  short: string;
  startCount: number;
  /** Inclusive. */
  endCount: number;
}

/**
 * Every part of the structure is a unit, and after every second one comes a join
 * that runs the dance from count 1 to there; the last join is the whole dance.
 * A default-named part of at most eight counts reads "8-count N"; anything the
 * learner renamed or merged keeps its own name or says its counts.
 */
export function lessonUnits(structure: LessonStructure): Unit[] {
  const ranges = partRanges(structure);
  const units: Unit[] = [];
  ranges.forEach((r, i) => {
    const n = i + 1;
    const custom = !/^Part \d+$/.test(r.part.name);
    const label = custom
      ? r.part.name
      : r.endCount - r.startCount < 8
        ? `8-count ${n}`
        : `Counts ${r.startCount}–${r.endCount}`;
    units.push({ id: `e${r.startCount}-${r.endCount}`, kind: "eight", label, short: String(n), startCount: r.startCount, endCount: r.endCount });
    const last = i === ranges.length - 1;
    if (ranges.length > 1 && (n % 2 === 0 || last)) {
      units.push({
        id: `j1-${r.endCount}`,
        kind: "join",
        label: last ? "Whole dance" : `Together 1 to ${n}`,
        short: last ? "All" : `1–${n}`,
        startCount: 1,
        endCount: r.endCount,
      });
    }
  });
  return units;
}

/**
 * The rounds for one unit. A join skips Watch (every piece of it has been watched)
 * and ramps in bigger steps, because it is two to eight times as long as an eight.
 */
export function schedule(kind: Unit["kind"]): Round[] {
  const rounds: Round[] = [];
  if (kind === "eight") rounds.push({ step: "watch", speed: 1 });
  for (let i = 0; i < (kind === "eight" ? SLOW_LOOPS : 1); i++) rounds.push({ step: "slow", speed: 0.5 });
  for (const speed of kind === "eight" ? rampSpeeds() : rampSpeeds(0.6, 1, 0.2)) rounds.push({ step: "build", speed });
  rounds.push({ step: "build", speed: 1, yourTurn: true });
  for (let i = 0; i < (kind === "eight" ? FULL_LOOPS : 1); i++) rounds.push({ step: "full", speed: 1 });
  return rounds;
}

/** Past the last round the unit is done: full speed, waiting for "Got it". */
export const isComplete = (rounds: readonly Round[], round: number) => round >= rounds.length;

export function roundAt(rounds: readonly Round[], round: number): Round {
  return rounds[Math.min(Math.max(round, 0), rounds.length - 1)];
}

/** Called once per loop wrap. Clamps at "complete" rather than running off. */
export function nextRound(rounds: readonly Round[], round: number): number {
  return Math.min(round + 1, rounds.length);
}

/** First round of a step — every rung of the ladder can be tapped, so power users can skip. */
export function stepStart(rounds: readonly Round[], step: Step): number {
  const i = rounds.findIndex((r) => r.step === step);
  return i < 0 ? 0 : i;
}

/** Loops done / loops in a step, for the pips. A step before the current one is full. */
export function stepProgress(rounds: readonly Round[], round: number, step: Step): { done: number; total: number } {
  let done = 0;
  let total = 0;
  rounds.forEach((r, i) => {
    if (r.step !== step) return;
    total++;
    if (i < round) done++;
  });
  return { done, total };
}

export const stepOf = (rounds: readonly Round[], round: number): Step | "done" =>
  isComplete(rounds, round) ? "done" : rounds[round].step;

// ------------------------------------------------------------------ learned

/**
 * Which units this browser has marked "Got it", per lesson. Same seam and same
 * reasoning as lib/structure.ts (no accounts yet, OPEN-DECISIONS D5): localStorage,
 * wrapped so private mode or a full quota costs the ticks, never the lesson.
 */
const LEARNED_KEY = (lessonId: string) => `stepwise.lesson-learned.v1.${lessonId}`;

export function loadLearned(lessonId: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(LEARNED_KEY(lessonId));
    const ids = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(ids) ? ids.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

export function saveLearned(lessonId: string, learned: ReadonlySet<string>): void {
  try {
    window.localStorage.setItem(LEARNED_KEY(lessonId), JSON.stringify([...learned]));
  } catch {
    /* see loadLearned */
  }
}
