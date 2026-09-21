/**
 * Pure logic for reading MotionResult v1. No three.js, no React — everything here
 * is unit-testable and is tested in motion.test.ts.
 */
import type { CropRect, MotionResult, Visibility } from "../../../packages/motion-contract/src/ts/generated/motion-result";
import { REGIONS } from "./regions";

export type { CropRect, MotionResult, Visibility };

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

export type CropRegion = "hands" | "feet";

/**
 * The `CropRect` in effect for one region at time `t`, or `null` when the
 * pipeline did not confidently localize it for that sample.
 *
 * Same step function as `sampleIndexAt`, for the same reason: a crop rectangle
 * is a per-frame fact from the detector, not a quantity to interpolate across a
 * `null` gap. A rect synthesised between two real localizations would be a
 * claim the pipeline never made (DESIGN.md §7h).
 */
export function cropRectAt(doc: MotionResult, personIndex: number, region: CropRegion, t: number): CropRect {
  const person = doc.persons[personIndex];
  if (!person) return null;
  return person.crop_rects[region][sampleIndexAt(doc.sample_times_s, t)] ?? null;
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

/**
 * `projectToFrame` in [0,1] frame coordinates, origin top-left — the same space
 * `CropRect` is expressed in, so a projected rectangle and a contract crop rectangle
 * are directly comparable.
 *
 * Normalized against `intrinsics.reference_*_px`, not `source_video.*_px`: the
 * contract says fx/fy/cx/cy were computed at the reference resolution and must be
 * scaled if they differ. Dividing by the reference dimensions is that scaling.
 */
export function projectToFrameNorm(
  doc: MotionResult,
  p: readonly [number, number, number],
): { x: number; y: number } | null {
  const uv = projectToFrame(doc, p);
  if (!uv) return null;
  const { reference_width_px, reference_height_px } = doc.camera.intrinsics;
  return { x: uv.x / reference_width_px, y: uv.y / reference_height_px };
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
  // In [0,1] frame space via projectToFrameNorm, so the intrinsics' reference
  // resolution is applied — mixing pixel coordinates from the intrinsics with
  // source_video's dimensions is only correct while the two happen to be equal.
  const halfDiagonal = Math.hypot(1, 1) / 2;
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
      const uv = projectToFrameNorm(doc, rt.position as [number, number, number]);
      if (!uv) continue;
      distSum += Math.hypot(uv.x - 0.5, uv.y - 0.5) / halfDiagonal;
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

/* --------------------------------------------------------------- follow rig */

/**
 * The follow camera is a SEPARATE AXIS from the view presets. A preset chooses the
 * direction you look FROM (azimuth/elevation, plus whatever the learner orbits to);
 * follow chooses what the camera looks AT and how far away it sits. They compose:
 * turning follow on never changes your angle, and orbiting never turns follow off.
 *
 * WHY THIS IS NOT A HARD LOCK. If the camera keeps the dancer pinned dead centre at a
 * fixed size, a dancer crossing three metres and a dancer standing still render
 * IDENTICALLY — the travel is erased, which is the same class of dishonesty as faking
 * a floor (DESIGN.md §7h, §10). So the rig is deliberately imperfect in two ways:
 *
 *   deadzone — the dancer may move freely inside a ball of this radius around the
 *              current aim point and the camera does not react AT ALL. Footwork in
 *              place, body sway and the ~0.2 m wander in today's pinned trajectories
 *              never move the camera. This is also what makes the whole feature a
 *              trivial no-op while OPEN-DECISIONS E6 (world placement) is unresolved:
 *              there is no separate "pinned" code path to get wrong.
 *   lag      — once the dancer does leave the deadzone the camera trails them by
 *              exactly `deadzone` and approaches with a time constant, so sustained
 *              travel visibly pushes the dancer off-centre and re-centres when they
 *              stop. Travel still reads.
 */
export interface FollowTuning {
  /**
   * Deadzone radius as a fraction of the height currently framed — NOT an absolute
   * distance. The `hands` and `feet` presets frame a box a fifth the size of the
   * body, and a deadzone tuned for a whole dancer would swallow every movement a
   * close-up exists to show. One fraction keeps every preset behaving the same way.
   */
  deadzoneFraction: number;
  /** Floor on the above, metres, so a degenerate box cannot produce a zero deadzone. */
  minDeadzone: number;
  /** Seconds to close ~63% of the remaining distance. Position. */
  tauPosition: number;
  /** Same, for the framing distance. Much slower — see below. */
  tauDistance: number;
  /** Switching between dancers further apart than this is a cut, not a glide. Metres. */
  cutDistance: number;
  /**
   * Hard ceiling on the lag above, as a MULTIPLE OF THE DEADZONE — so it scales with
   * the framing the same way the deadzone does, and a close-up gets a proportionally
   * tighter one.
   *
   * The lag is `deadzone + speed * tauPosition` at steady state and is otherwise
   * unbounded, which was fine for as long as nothing in the repo travelled faster
   * than the synthetic fixture (under 1 m/s). Real output is not that. Measured on
   * the shipped solo-01 document: the dancer sustains **4.42 m/s** over a one-second
   * window, which at `tauPosition` 0.45 s trails the camera by 0.35 + 1.99 = 2.34 m
   * while the rig frames from ~3.6 m at a 16-degree horizontal half-angle. That is
   * 33 degrees off axis: the dancer is not merely off-centre, they are outside the
   * panel entirely, which is the exact failure the follow camera exists to prevent.
   */
  maxLagFactor: number;
}

/**
 * Tuned on the travelling fixture at both widths (see the report).
 *
 * `deadzoneFraction` 0.19 — about 0.35 m on a 1.85 m dancer, a little wider than a
 * dancer's own lateral sway and wider than the ~0.2 m wander the shipped fixtures
 * contain, so today the camera does not move at all.
 *
 * `tauPosition` 0.45 s: fast enough that a dancer who walks two metres is not left
 * clipped against the panel edge, slow enough that the displacement is plainly
 * visible for about a second first. Under 0.2 s the travel stops reading; over ~0.8 s
 * the dancer reaches the panel edge before the camera commits.
 *
 * `tauDistance` 2.0 s, four times slower, and this asymmetry is the point: the body's
 * bounding box changes shape every time an arm goes up, and matching that at position
 * speed makes the camera breathe in and out continuously — far more distracting than
 * the drift it was meant to fix. At 2 s the rig ignores pose and only answers genuine
 * changes of depth.
 *
 * `maxLagFactor` 1.6 — 0.56 m at body framing.
 *
 * Where 1.6 comes from, rather than taste: the body preset frames from 3.57 m at
 * fov 34, and the narrowest panel that matters (a 390 px phone, compare mode on, so
 * ~0.85 aspect) has a horizontal half-frame of 0.93 m there. A dancer is about 0.4 m
 * half-width, so the aim point has to stay inside ~0.55 m or part of the body is off
 * the panel. 1.6 x deadzone is 0.56 m, and it scales with the framing exactly as the
 * deadzone does, so a close-up inherits a proportionally tighter ceiling instead of
 * an absolute one tuned for a whole body.
 *
 * It binds above 0.47 m/s — i.e. not only at solo-01's sprint but also on the
 * travelling fixture's 1.21 m/s peak, where the unclamped lag was 0.90 m and already
 * put the dancer's leading edge off a phone panel. That was a latent bug, not a
 * regression introduced here; the fixture was only ever checked with follow on at
 * desktop width. What the ceiling costs is the last of the lag cue at speed; what
 * pays for it is the floor, which is now drawn from the real fitted plane and is
 * world-fixed, and which DESIGN.md §9 already names as the thing that makes travel
 * legible.
 */
export const FOLLOW: FollowTuning = {
  deadzoneFraction: 0.19,
  minDeadzone: 0.05,
  tauPosition: 0.45,
  tauDistance: 2.0,
  cutDistance: 2.5,
  maxLagFactor: 1.6,
};

/** A typical framed body height, metres — only used to state the deadzone in metres. */
export const BODY_HEIGHT_M = 1.85;

export function deadzoneFor(framedHeight: number, tuning: FollowTuning = FOLLOW): number {
  return Math.max(tuning.deadzoneFraction * framedHeight, tuning.minDeadzone);
}

/** Frame-rate-independent exponential approach. `tau` = seconds to close ~63%. */
export function damp(current: number, target: number, tau: number, dt: number): number {
  if (tau <= 0) return target;
  return target + (current - target) * Math.exp(-dt / tau);
}

export type Vec3 = [number, number, number];

/**
 * One follow step: deadzone, then damped approach. Returns the new camera aim point.
 *
 * `dt` is clamped — a backgrounded tab hands back a delta of seconds, and an
 * un-clamped exponential then teleports the camera on the first frame after you
 * return to it.
 */
export function followStep(
  current: Vec3,
  subject: Vec3,
  deadzone: number,
  dt: number,
  tuning: FollowTuning = FOLLOW,
): Vec3 {
  const d: Vec3 = [current[0] - subject[0], current[1] - subject[1], current[2] - subject[2]];
  const len = Math.hypot(d[0], d[1], d[2]);
  if (len <= deadzone) return current;
  // Aim at the EDGE of the deadzone, not at the dancer: at steady state the camera
  // trails by exactly `deadzone`, which is the lag that keeps travel legible.
  const k = deadzone / len;
  const aim: Vec3 = [subject[0] + d[0] * k, subject[1] + d[1] * k, subject[2] + d[2] * k];
  const step = Math.min(dt, 0.1);
  const next: Vec3 = [
    damp(current[0], aim[0], tuning.tauPosition, step),
    damp(current[1], aim[1], tuning.tauPosition, step),
    damp(current[2], aim[2], tuning.tauPosition, step),
  ];
  // Ceiling on the trail. Applied AFTER the damp rather than by shortening tau, so
  // ordinary travel keeps its measured easing and only a sprint is caught — see
  // FOLLOW.maxLagFactor. Clamped rather than snapped: the camera still arrives late,
  // it just cannot be left behind.
  const maxLag = deadzone * tuning.maxLagFactor;
  const trail: Vec3 = [next[0] - subject[0], next[1] - subject[1], next[2] - subject[2]];
  const trailLen = Math.hypot(trail[0], trail[1], trail[2]);
  if (trailLen <= maxLag) return next;
  const c = maxLag / trailLen;
  return [subject[0] + trail[0] * c, subject[1] + trail[1] * c, subject[2] + trail[2] * c];
}

/* ------------------------------------------------------- world placement */

/**
 * Did the pipeline ever solve a world position for this dancer (OPEN-DECISIONS E6)?
 *
 * THE GATE FOR DRAWING A DANCER ANYWHERE BUT WHERE THE CLIP PUTS THEM. A track too
 * short to place — under `world_placement_probe`'s 25-frame minimum, e.g. solo-07's
 * tracks 5 and 9 at 21 and 14 frames — still carries a `root_trajectory`, because
 * the contract requires a Vec3 on every sample. That Vec3 is `skel_state`'s pinned
 * character-local constant, and in this document's world space it is **not a place
 * in the room**: on solo-07 it sits 2.16 m above the fitted floor, next to the
 * camera. `motion_result.py` says so the only way it can, by never marking any of
 * those samples `observed`.
 *
 * So: any `observed` root sample at all means the solve ran and the trajectory is a
 * claim about the room. None means it never ran, and the honest render is to leave
 * the dancer exactly where the animation clip puts them — a dancer who does not
 * travel is a visible limitation; a dancer flung two metres into the air is a
 * confident lie (DESIGN.md §7h).
 *
 * Back-filled and held samples inside a placed track are deliberately NOT excluded.
 * They are `observed: false` too, but their position is a real solved placement
 * carried forward, which is why `motion_result.py` back-fills rather than leaving
 * the leading gap on the constant.
 */
export function rootPlacementObserved(doc: MotionResult, personIndex: number): boolean {
  return doc.persons[personIndex].root_trajectory.some((s) => s.provenance.observed);
}

/**
 * This dancer's world root position at time `t`, LINEARLY INTERPOLATED between the
 * two samples either side.
 *
 * Interpolated, unlike `sampleIndexAt`'s step lookup, and the difference is not an
 * inconsistency — it is what keeps the mesh and its placement on one clock. The GLB
 * root's pose is sampled by `AnimationMixer` from LINEAR channels keyed at exactly
 * `sample_times_s` (verify_glb.py: 218/218 LINEAR). Stepping the offset at 15 Hz
 * while the mixer lerps the pose at display rate would make the body swim inside its
 * own placement — the desync reads as "the mesh feels laggy", not as an obvious bug.
 * Lerping the same channel the same way means the two agree at every instant, not
 * just at keyframes.
 *
 * This does not reopen the "never interpolate across a suppressed span" rule, which
 * is about visibility: a held span's positions are already constant (the pipeline
 * forward-fills them), so lerping across one is the identity.
 */
export function rootPositionAt(doc: MotionResult, personIndex: number, t: number): Vec3 {
  const times = doc.sample_times_s;
  const rt = doc.persons[personIndex].root_trajectory;
  const i = sampleIndexAt(times, t);
  const a = rt[i].position;
  const b = rt[i + 1]?.position;
  // Last sample, or a zero-length span in a malformed timeline: hold, never divide.
  const span = b ? times[i + 1] - times[i] : 0;
  if (!b || span <= 0) return [a[0], a[1], a[2]];
  const u = Math.min(Math.max((t - times[i]) / span, 0), 1);
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
}

/**
 * How far across the floor this dancer ranges over the whole clip, in metres: the
 * diagonal of the bounding rectangle of `root_trajectory` on the ground plane.
 *
 * Whole-clip and therefore stable — a per-frame number would flicker in a label that
 * DESIGN.md §8 wants readable from three metres away. Y is ignored on purpose: a
 * dancer who jumps has not travelled.
 *
 * NOTE (OPEN-DECISIONS E6): this used to read "~0.2 m on every real clip, because
 * `root_trajectory` is pinned to the origin". That stopped being true on branch
 * `grounding-wiring`: `motion_result` now composes a real per-frame world placement,
 * and solo-01 measures metres of travel rather than centimetres of sway. The gate is
 * still right, though, and for a reason the old note did not give: a track too short
 * to place (under 25 frames) still falls back to the pinned constant, so a document
 * can carry a real trajectory for one dancer and a placeholder for another. Reading
 * provenance is what tells them apart; `travelsMeaningfully` is the cheap version of
 * that, and it still beats printing "0.0 m" and implying we measured stillness.
 */
export function travelExtent(doc: MotionResult, personIndex: number): number {
  const rt = doc.persons[personIndex].root_trajectory;
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (const s of rt) {
    minX = Math.min(minX, s.position[0]);
    maxX = Math.max(maxX, s.position[0]);
    minZ = Math.min(minZ, s.position[2]);
    maxZ = Math.max(maxZ, s.position[2]);
  }
  return Math.hypot(maxX - minX, maxZ - minZ);
}

/**
 * Whether the document carries enough travel to be worth telling the learner about.
 * The threshold is the follow deadzone: below it the camera never moves anyway, so
 * claiming a distance would describe something the learner cannot see.
 */
export function travelsMeaningfully(doc: MotionResult, personIndex: number): boolean {
  return travelExtent(doc, personIndex) > deadzoneFor(BODY_HEIGHT_M);
}

/* ------------------------------------------------------- video crop-follow */

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Project an axis-aligned world box into the source frame and return its [0,1]
 * bounding rectangle — the body-follow crop for the video pane.
 *
 * WHY THIS AND NOT `crop_rects`. The frozen v1 contract only carries `crop_rects.hands`
 * and `crop_rects.feet`; there is no body rectangle, and unioning hands with feet is
 * both wrong (it misses a raised head, and both are null on the `failure-lesson`
 * fixture for most of the clip) and a second source of truth that can drift from the
 * 3D pane. Projecting the SAME world bounds the 3D camera frames, through the clip's
 * own camera, keeps the two panes in sync BY CONSTRUCTION — the video crop and the
 * 3D framing are computed from one number. If the camera solve is wrong the crop is
 * wrong in exactly the same way the 3D pane is, which is the failure mode you want.
 *
 * Returns null if any corner is at or behind the camera plane, where the projection
 * is meaningless. Callers must hold their last good rectangle rather than jump.
 *
 * KNOWN CONSERVATISM: the screen-space bounding box of a projected world box is
 * larger than the dancer's actual silhouette — the near face projects bigger than the
 * far face, so a ~0.5 m deep body over-covers by roughly 15% at 3 m. The crop is
 * therefore slightly wider than it strictly needs to be, and the "at the edge of the
 * shot" warning fires slightly early. Both errors point the safe way for §7h: show
 * marginally more real frame than needed, and warn marginally sooner. Tightening this
 * means projecting the joints themselves, which is only worth it if the slack is ever
 * measured to matter.
 */
export function projectBoxToFrame(doc: MotionResult, min: Vec3, max: Vec3): Rect | null {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let c = 0; c < 8; c++) {
    const uv = projectToFrameNorm(doc, [
      c & 1 ? max[0] : min[0],
      c & 2 ? max[1] : min[1],
      c & 4 ? max[2] : min[2],
    ]);
    if (!uv) return null;
    x0 = Math.min(x0, uv.x); y0 = Math.min(y0, uv.y);
    x1 = Math.max(x1, uv.x); y1 = Math.max(y1, uv.y);
  }
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/** Never magnify the source more than this. See `cropTransform`. */
export const MAX_CROP_ZOOM = 2.5;
/** Fraction of the pane's height the dancer is framed to fill. */
export const CROP_TARGET_HEIGHT = 0.72;

export interface CropWindow {
  /** Uniform magnification of the video element, >= 1. */
  zoom: number;
  /** Pan, as a fraction of the un-scaled element box, applied before the scale. */
  tx: number;
  ty: number;
  /** True when the dancer's projected box is not wholly inside the source frame. */
  clipped: boolean;
}

export const NO_CROP: CropWindow = { zoom: 1, tx: 0, ty: 0, clipped: false };

/**
 * Turn a projected body rectangle into a crop window for the video element.
 *
 * THE HONESTY CONSTRAINT (DESIGN.md §7h). Two rules, both hard:
 *
 *  1. `zoom` is never below 1. Zooming OUT would have to invent pixels outside the
 *     frame the phone actually shot.
 *  2. The visible window is clamped to stay INSIDE the source frame. When the dancer
 *     walks toward the edge the window stops at the edge and the dancer slides off
 *     centre — it never keeps panning and pads with black, and it never zooms further
 *     to hide the fact that the dancer is leaving. A dancer at the edge of frame LOOKS
 *     like a dancer at the edge of frame. `clipped` reports that so the caller can
 *     say so in words too.
 *
 * `MAX_CROP_ZOOM` is a second, softer limit: past ~2.5x a 1080-wide phone clip is
 * visibly upscaled, and a blurry crop implies detail the source never had.
 */
export function cropTransform(body: Rect | null): CropWindow {
  if (!body || body.height <= 0) return NO_CROP;
  const zoom = Math.min(Math.max(CROP_TARGET_HEIGHT / body.height, 1), MAX_CROP_ZOOM);
  const half = 0.5 / zoom; // half-extent of the visible window, in frame fractions
  const cx = body.x + body.width / 2;
  const cy = body.y + body.height / 2;
  // Rule 2: the window centre cannot go closer to an edge than its own half-extent.
  const px = half >= 0.5 ? 0.5 : Math.min(Math.max(cx, half), 1 - half);
  const py = half >= 0.5 ? 0.5 : Math.min(Math.max(cy, half), 1 - half);
  return {
    zoom,
    // `transform: translate(tx, ty) scale(zoom)` maps frame point p to
    // zoom * (p - 0.5) + t; solving for the dancer landing at the centre gives this.
    tx: -zoom * (px - 0.5),
    ty: -zoom * (py - 0.5),
    clipped: body.x < 0 || body.y < 0 || body.x + body.width > 1 || body.y + body.height > 1,
  };
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
