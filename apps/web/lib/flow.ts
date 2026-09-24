/**
 * The processing screen's arithmetic: "practice while it builds" (flow
 * redesign, direction B with A's step results).
 *
 * Pure, so `test/flow.test.ts` covers it without a DOM. Everything here works
 * on the RAW video's own timeline, before any MotionResult exists.
 */
import type { CountGrid, LoopSpan } from "../../../packages/navigation/src/core";
import { countAtTime, timeOfCount } from "../../../packages/navigation/src/core";
import type { JobStatus } from "./jobStatus";
import { processing as copy } from "./copy";

export type Counts = NonNullable<NonNullable<JobStatus["milestones"]>["counts"]>;

/**
 * The milestone's beat proposal as a grid on this clip. Same derivation as
 * services/motion-api/motion_result.py `_proposed_counts` (count 1 clamped to
 * the start, total re-derived against the timeline end) so the counts a
 * learner practises here are the counts the lesson opens on. The end here is
 * the video's duration rather than the last sample slot; the two differ by
 * under one sample, which can move the last count by one at most.
 */
export function gridFromCounts(counts: Counts, durationS: number): CountGrid {
  const countOneS = Math.max(0, counts.count_one_s);
  const spc = counts.seconds_per_count;
  return {
    countOneS,
    secondsPerCount: spc,
    countTotal: Math.max(1, Math.floor((durationS - countOneS) / spc) + 1),
  };
}

export const eightTotal = (grid: CountGrid) => Math.ceil(grid.countTotal / 8);

/** 1-based eight-count under the playhead, clamped to the dance. */
export function eightAt(grid: CountGrid, t: number): number {
  const count = Math.floor(countAtTime(grid, t));
  return Math.min(eightTotal(grid), Math.max(1, Math.floor((count - 1) / 8) + 1));
}

export function eightSpan(grid: CountGrid, n: number): LoopSpan {
  return { startCount: n * 8 - 7, endCount: Math.min(grid.countTotal, n * 8) };
}

/** [start, end) seconds of eight-count n, kept inside the clip. */
export function eightTimes(grid: CountGrid, n: number, durationS: number): [number, number] {
  const { startCount, endCount } = eightSpan(grid, n);
  return [Math.max(0, timeOfCount(grid, startCount)), Math.min(durationS, timeOfCount(grid, endCount + 1))];
}

/** 0–7 for the count strip, or -1 in the lead-in before count 1. */
export function stripIndex(grid: CountGrid, t: number): number {
  const count = Math.floor(countAtTime(grid, t));
  if (count < 1) return -1;
  return (Math.min(count, grid.countTotal) - 1) % 8;
}

/** Where the dot sits along the eight ticks, 0..1: across the active count's own tick. */
export function stripPosition(grid: CountGrid, t: number): number {
  const c = countAtTime(grid, t) - 1;
  if (c < 0) return 0;
  return (((c % 8) + 8) % 8) / 8;
}

export const perMinute = (counts: Counts) => Math.round(60 / counts.seconds_per_count);

// ------------------------------------------------------------------ steps

export type StepState = "done" | "now" | "wait";
export interface Step {
  key: "clip" | "dancers" | "counts" | "body";
  label: string;
  state: StepState;
  note: string;
}

/**
 * A's four steps, each with the real result it produced. Every "done" here is
 * driven by a milestone the service actually sent; `progress` only decides
 * which unfinished step is "now". process_clip's fractions: detecting is
 * 0.10–0.25, building the body 0.25–0.95, the 3D file 0.97.
 */
export function flowSteps(status: JobStatus | null, grid: CountGrid | null): Step[] {
  const m = status?.milestones ?? {};
  const state = status?.state ?? "queued";
  const p = status?.progress ?? 0;
  const done = state === "succeeded";
  const s = copy.steps;

  const dancers: Step =
    m.dancers != null
      ? { key: "dancers", label: s.dancers, state: "done", note: s.dancersFound(m.dancers) }
      : state === "processing" && p >= 0.1
        ? { key: "dancers", label: s.dancers, state: "now", note: s.looking }
        : { key: "dancers", label: s.dancers, state: done ? "done" : "wait", note: "" };

  const counts: Step = m.counts
    ? {
        key: "counts",
        label: s.counts,
        state: "done",
        note: grid ? s.countsFound(perMinute(m.counts), eightTotal(grid)) : s.countsTempo(perMinute(m.counts)),
      }
    : done
      ? { key: "counts", label: s.counts, state: "done", note: s.countsInLesson }
      : { key: "counts", label: s.counts, state: "now", note: m.frames_done != null ? s.noneYet : s.listening };

  let body: Step;
  if (done) body = { key: "body", label: s.body, state: "done", note: s.ready };
  else if (m.frames_done != null && m.frames_total) {
    body = { key: "body", label: s.body, state: "now", note: builtNote(m.frames_done, m.frames_total, grid) };
  } else if (state === "processing" && p >= 0.95) {
    body = { key: "body", label: s.body, state: "now", note: s.finishing };
  } else body = { key: "body", label: s.body, state: "wait", note: "" };

  return [{ key: "clip", label: s.clip, state: "done", note: s.playing }, dancers, counts, body];
}

/**
 * "3 of 8 eight-counts" when the counts are known, else frames. Built frames
 * span the clip evenly (15 fps sampling), so the fraction of frames done is
 * the fraction of the clip's timeline built.
 */
export function builtNote(framesDone: number, framesTotal: number, grid: CountGrid | null): string {
  if (!grid) return copy.steps.frames(framesDone, framesTotal);
  const eights = eightTotal(grid);
  const lastCount = Math.floor((framesDone / framesTotal) * grid.countTotal);
  return copy.steps.eights(Math.min(eights, Math.floor(lastCount / 8)), eights);
}

// ---------------------------------------------------------------- handoff

/**
 * Into the lesson, carrying the speed and the loop the learner was on. Query
 * params rather than sessionStorage: they survive a reload and a copied link,
 * and the lesson ignores anything it does not recognise.
 */
export function handoffHref(jobId: string, speed: number, loop: LoopSpan | null): string {
  const q = new URLSearchParams();
  if (speed !== 1) q.set("speed", String(speed));
  if (loop) q.set("loop", `${loop.startCount}-${loop.endCount}`);
  const s = q.toString();
  return `/lesson/${encodeURIComponent(jobId)}${s ? `?${s}` : ""}`;
}

/** The lesson's side of `handoffHref`. Unknown speeds and bad loops are dropped. */
export function parseHandoff(
  search: string,
  speeds: readonly number[],
  countTotal: number,
): { speed: number | null; loop: LoopSpan | null } {
  const q = new URLSearchParams(search);
  const sp = Number(q.get("speed"));
  const speed = speeds.includes(sp) ? sp : null;
  const m = /^(\d+)-(\d+)$/.exec(q.get("loop") ?? "");
  let loop: LoopSpan | null = null;
  if (m) {
    const a = Number(m[1]);
    const b = Math.min(Number(m[2]), countTotal);
    if (a >= 1 && a <= b) loop = { startCount: a, endCount: b };
  }
  return { speed, loop };
}

// ------------------------------------------------------------- detections

/** GET /jobs/{id}/detections — see services/motion-api/milestones.py. */
export interface Detections {
  fps: number;
  width: number;
  height: number;
  times: number[];
  dancers: { id: number; points: (([number, number] | null)[] | null)[] }[];
}

/** Index of the detection sample nearest `t`, or -1 past the sampled range. */
export function detectionIndex(d: Detections, t: number): number {
  if (!d.times.length) return -1;
  const i = Math.round((t - d.times[0]) * d.fps);
  if (i < 0) return 0;
  return i < d.times.length ? i : -1;
}

/** COCO-17 limbs. Face points beyond the nose are left out: noise at this size. */
export const COCO_BONES: [number, number][] = [
  [5, 7], [7, 9], [6, 8], [8, 10], [5, 6], [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
];
