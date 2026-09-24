/**
 * The processing screen's arithmetic, pure so `test/flow.test.ts` covers it
 * without a DOM.
 *
 * No count grid lives here any more. The screen used to turn
 * `milestones.counts` into an early 8-count practice on the raw video; the
 * owner removed it (2026-09-23) because those early counts were often off the
 * beat and put count 1 on the intro. The helpers for it (gridFromCounts,
 * eightAt, eightTimes, the count strip) are in git history before the A2
 * build, for when count 1 is reliable enough to bring the practice back.
 */
import type { LoopSpan } from "../../../packages/navigation/src/core";
import type { JobStatus } from "./jobStatus";
import { processing as copy } from "./copy";

// ------------------------------------------------------------------ steps

export type StepState = "done" | "now" | "wait";
export interface Step {
  key: "clip" | "dancers" | "body";
  label: string;
  state: StepState;
  note: string;
}

/**
 * Three steps, each with the real result it produced. Every "done" here is
 * driven by a milestone the service actually sent (or by success itself);
 * `progress` only decides which unfinished step is "now". process_clip's
 * fractions: detecting is 0.10–0.25, building the body 0.25–0.95, the 3D file
 * 0.97.
 */
export function flowSteps(status: JobStatus | null): Step[] {
  const m = status?.milestones ?? {};
  const state = status?.state ?? "queued";
  const p = status?.progress ?? 0;
  const done = state === "succeeded";
  const s = copy.steps;

  const dancers: Step =
    m.dancers != null
      ? { key: "dancers", label: s.dancers, state: "done", note: s.dancersFound(m.dancers) }
      : done
        ? { key: "dancers", label: s.dancers, state: "done", note: "" }
        : state === "processing" && p >= 0.1
          ? { key: "dancers", label: s.dancers, state: "now", note: s.looking }
          : { key: "dancers", label: s.dancers, state: "wait", note: s.waiting };

  let body: Step;
  if (done) body = { key: "body", label: s.body, state: "done", note: s.ready };
  else if (m.frames_done != null && m.frames_total) {
    body = { key: "body", label: s.body, state: "now", note: s.frames(m.frames_done, m.frames_total) };
  } else if (state === "processing" && p >= 0.95) {
    body = { key: "body", label: s.body, state: "now", note: s.finishing };
  } else body = { key: "body", label: s.body, state: "wait", note: s.waiting };

  return [{ key: "clip", label: s.clip, state: "done", note: s.playing }, dancers, body];
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
