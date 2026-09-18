/**
 * Pure logic for reading MotionResult v1. No three.js, no React — everything here
 * is unit-testable and is tested in motion.test.ts.
 */
import type { MotionResult, Visibility } from "../../../packages/motion-contract/src/ts/generated/motion-result";
import { REGIONS } from "./regions";

export type { MotionResult, Visibility };

/* ------------------------------------------------------------------- seeking */

/**
 * Index of the sample in effect at time `t`, found by searching `sample_times_s`.
 *
 * This is THE seeking primitive. Never `Math.round(t * fps_nominal)` — frame drops,
 * variable-rate ingest and suppression all break that arithmetic, which is exactly
 * why the contract calls sample_times_s its most important field. The lookup is a
 * step function on purpose: visibility must never be interpolated across a
 * suppressed span.
 */
export function sampleIndexAt(times: readonly number[], t: number): number {
  if (t <= times[0]) return 0;
  if (t >= times[times.length - 1]) return times.length - 1;
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/* ---------------------------------------------------------------- visibility */

const RANK: Record<Visibility, number> = { observed: 0, uncertain: 1, absent: 2 };

export function worstVisibility(a: Visibility, b: Visibility): Visibility {
  return RANK[a] >= RANK[b] ? a : b;
}

/**
 * Visibility of every drawable region for one person at one sample, keyed by region id.
 *
 * Conservative, and conservative in one direction only: a region inherits the worst
 * visibility along the joint chain from the root down to its own bone (PRD §4 —
 * "a suppressed wrist suppresses the whole hand"). It does NOT inherit from its
 * children, so a shin whose ankle went out of frame still renders: the shin was
 * seen, and hiding it would under-claim case 1 (DESIGN.md §7h).
 */
export function regionVisibility(doc: MotionResult, personIndex: number, sampleIndex: number): Map<string, Visibility> {
  const joints = doc.joint_hierarchy.joints;
  const byName = new Map(joints.map((j) => [j.name, j.index]));
  const sample = doc.persons[personIndex].samples[sampleIndex];

  const chainWorst: Visibility[] = new Array(joints.length);
  // joints are ordered by index and a parent's index is always < its child's in a
  // well-formed hierarchy, but do not rely on it — resolve recursively with memo.
  const resolve = (i: number): Visibility => {
    const memo = chainWorst[i];
    if (memo) return memo;
    const own = sample.joints[i].visibility;
    const parent = joints[i].parent_index;
    const v = parent >= 0 ? worstVisibility(own, resolve(parent)) : own;
    chainWorst[i] = v;
    return v;
  };

  const out = new Map<string, Visibility>();
  for (const region of REGIONS) {
    const idx = byName.get(region.bone);
    out.set(region.id, idx === undefined ? "absent" : resolve(idx));
  }
  return out;
}

/** Plain-language notes for regions that are not drawn, e.g. "left foot not in frame". */
export function absentNotes(vis: Map<string, Visibility>): string[] {
  return REGIONS.filter((r) => vis.get(r.id) === "absent").map((r) => `${r.label} not in frame`);
}

/* ------------------------------------------------------------------- dancers */

/** DESIGN.md §3 — differ in both hue and lightness, so they survive CVD and sunlight. */
export const DANCER_COLORS = ["#E8952F", "#1E7A6F", "#C2417E", "#3F51B5"];

/**
 * The colour a dancer renders in. One accent on screen at a time (DESIGN.md §3):
 * only the selected dancer is saturated, everyone else is a muted neutral.
 *
 * With a single dancer the per-clip sampled accent wins; with more than one the
 * contract's `accent_color.source` is "fallback" and the fixed swatches are used.
 */
export function dancerColor(doc: MotionResult, personIndex: number, selectedIndex: number): string {
  if (personIndex !== selectedIndex) return "#6E675F";
  if (doc.persons.length === 1 && doc.accent_color.source === "sampled") return doc.accent_color.hex;
  return DANCER_COLORS[personIndex % DANCER_COLORS.length];
}

/** Project a world point through the clip's static pinhole camera to pixel coords. */
export function projectToFrame(doc: MotionResult, p: readonly [number, number, number]): { x: number; y: number } | null {
  const m = doc.camera.camera_to_world; // column-major 4x4
  // World -> camera is the inverse. The transform is rigid (rotation + translation),
  // so the inverse is R^T * (p - t) — no general matrix inversion needed.
  const t = [m[12], m[13], m[14]];
  const d = [p[0] - t[0], p[1] - t[1], p[2] - t[2]];
  const cam = [
    m[0] * d[0] + m[1] * d[1] + m[2] * d[2],
    m[4] * d[0] + m[5] * d[1] + m[6] * d[2],
    m[8] * d[0] + m[9] * d[1] + m[10] * d[2],
  ];
  // glTF/three camera convention: looks down -Z, so a point in front has cam.z < 0.
  const depth = -cam[2];
  if (depth <= 1e-6) return null;
  const { fx, fy, cx, cy } = doc.camera.intrinsics;
  return { x: cx + (fx * cam[0]) / depth, y: cy - (fy * cam[1]) / depth };
}

export interface DancerScore {
  personIndex: number;
  /** Fraction of joint-samples that are `observed`. */
  coverage: number;
  /** 0 = dead centre of frame, 1 = at the frame edge. */
  centreDistance: number;
  score: number;
}

/**
 * DESIGN.md §7a2 default selection: "the dancer nearest the frame centre with the
 * highest coverage and confidence".
 *
 * Two quantities, so they need weighting, and the doc does not give one. Coverage
 * leads because a well-centred dancer the model barely saw is a worse lesson than a
 * slightly off-centre one it tracked cleanly; centre distance breaks ties and
 * handles the common case of a deliberately framed dancer beside a bystander.
 * ponytail: if this picks wrong on real clips, the weight is the one knob to turn.
 */
export function scoreDancers(doc: MotionResult): DancerScore[] {
  const halfDiagonal = Math.hypot(doc.source_video.width_px, doc.source_video.height_px) / 2;
  return doc.persons.map((person, personIndex) => {
    let observed = 0;
    let total = 0;
    for (const sample of person.samples) {
      for (const joint of sample.joints) {
        total++;
        if (joint.visibility === "observed") observed++;
      }
    }
    let distSum = 0;
    let distCount = 0;
    for (const rt of person.root_trajectory) {
      const uv = projectToFrame(doc, rt.position as [number, number, number]);
      if (!uv) continue;
      distSum += Math.hypot(uv.x - doc.source_video.width_px / 2, uv.y - doc.source_video.height_px / 2) / halfDiagonal;
      distCount++;
    }
    const coverage = total === 0 ? 0 : observed / total;
    const centreDistance = distCount === 0 ? 1 : Math.min(distSum / distCount, 1);
    return { personIndex, coverage, centreDistance, score: coverage - 0.5 * centreDistance };
  });
}

export function defaultPersonIndex(doc: MotionResult): number {
  return scoreDancers(doc).reduce((best, d) => (d.score > best.score ? d : best)).personIndex;
}

/* -------------------------------------------------------------- view presets */

export type ViewId = "camera" | "front" | "back" | "side" | "top" | "hands" | "feet";

export interface ViewPreset {
  id: ViewId;
  label: string;
  /** Radians, 0 = in front of the dancer (+Z), measured about +Y. */
  azimuth: number;
  /** Radians above the horizon. */
  elevation: number;
  /** Extra margin on the distance that frames `focus` — 1 is a tight fit. */
  distance: number;
  focus: "body" | "hands" | "feet";
}

export const VIEW_PRESETS: ViewPreset[] = [
  { id: "camera", label: "camera", azimuth: 0, elevation: 0.14, distance: 1, focus: "body" },
  { id: "front", label: "front", azimuth: 0, elevation: 0.1, distance: 0.95, focus: "body" },
  { id: "back", label: "back", azimuth: Math.PI, elevation: 0.1, distance: 0.95, focus: "body" },
  { id: "side", label: "side", azimuth: Math.PI / 2, elevation: 0.1, distance: 0.95, focus: "body" },
  { id: "top", label: "top", azimuth: 0, elevation: 1.32, distance: 1.05, focus: "body" },
  { id: "hands", label: "hands", azimuth: 0, elevation: 0.05, distance: 1.6, focus: "hands" },
  { id: "feet", label: "feet", azimuth: 0.35, elevation: 0.42, distance: 1.7, focus: "feet" },
];

/**
 * DESIGN.md §4: the front view is camera evidence; every other viewpoint is
 * synthesised from a tracked body and is labelled "estimated view". "camera" is the
 * only preset that is not estimated — "front" is a synthesised approximation of it
 * and is labelled as such, because the real camera is rarely exactly head-on.
 */
export function viewLabel(view: ViewId, mirrored: boolean): string {
  const preset = VIEW_PRESETS.find((p) => p.id === view)!;
  const kind = view === "camera" ? "camera view" : "estimated view";
  return mirrored ? `${preset.label} · mirrored · ${kind}` : `${preset.label} · ${kind}`;
}

export const SPEEDS = [0.25, 0.5, 0.75, 1] as const;
