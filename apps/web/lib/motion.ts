/**
 * Pure logic for reading MotionResult v1. No three.js, no React — everything here
 * is unit-testable and is tested in motion.test.ts.
 */
import type { CropRect, MotionResult, Visibility } from "../../../packages/motion-contract/src/ts/generated/motion-result";
import { jointWorldPosition } from "./footContact";
import { FOOT_JOINTS, REGIONS, lookupJoint } from "./regions";

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

export type CropRegion = "hands" | "feet" | "left_hand" | "right_hand" | "left_foot" | "right_foot";

/**
 * Which close-ups to show for one dancer, in screen order. Per-side rects when the
 * lesson carries them (the contract's optional `left_hand`..`right_foot`), else the
 * combined `hands`/`feet` older lessons have. Left/right are the DANCER's, so they
 * are ordered as they sit on screen for a dancer facing the camera: their right
 * hand is on screen-left, unless the video is mirrored.
 */
export function cropRegions(doc: MotionResult, personIndex: number, mirrored: boolean): CropRegion[] {
  if (!doc.persons[personIndex]?.crop_rects.left_hand) return ["hands", "feet"];
  return mirrored
    ? ["left_hand", "right_hand", "left_foot", "right_foot"]
    : ["right_hand", "left_hand", "right_foot", "left_foot"];
}

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
  return person.crop_rects[region]?.[sampleIndexAt(doc.sample_times_s, t)] ?? null;
}

/**
 * Fraction of a region's own rects the steady crop is sized to hold. See `steadyCropTrack`.
 * 0.9, measured on a real 33 s solo clip: holds >= 70% of the raw hands rect on every
 * frame (p75 drops below that on 3%); the cost is ~1.2x less magnification than p75.
 */
export const STEADY_CROP_SIZE_QUANTILE = 0.9;
/** Gaussian sigma, seconds, on the crop centre. Reduced motion pans half as fast. */
export const STEADY_CROP_SIGMA_S = 0.3;
export const STEADY_CROP_SIGMA_REDUCED_S = 0.6;

/**
 * The raw `crop_rects` are unwatchable as a close-up: `hands` is ONE rect around
 * BOTH hands, so its size swings ~9x as the arms open and close (p95 frame-to-frame
 * zoom change 52% on a real clip) and its centre jumps half a crop width per sample
 * at p95. So the peek is steadied offline — the whole track is known up front:
 *
 *  - ONE square size per person per region for the whole clip (the
 *    `STEADY_CROP_SIZE_QUANTILE` of the rects' longer sides), so the zoom never moves.
 *  - The centre is a zero-phase Gaussian average over time (no lag, unlike any
 *    causal damper), taken only WITHIN a contiguous run of real rects: a `null`
 *    stays `null` and nothing is averaged across it (DESIGN.md §7h).
 *  - The square is clamped inside the frame, never padded past it.
 *
 * Measured result: centre step p95 0.52 -> 0.05 of the crop size, zoom change 0.
 */
export function steadyCropTrack(
  doc: MotionResult,
  personIndex: number,
  region: CropRegion,
  sigmaS: number = STEADY_CROP_SIGMA_S,
): CropRect[] {
  const rects = doc.persons[personIndex]?.crop_rects[region] ?? [];
  const times = doc.sample_times_s;
  const { width_px: W, height_px: H } = doc.source_video;
  const sides = rects.flatMap((r) => (r ? [Math.max(r.width * W, r.height * H)] : [])).sort((a, b) => a - b);
  if (!sides.length) return rects.map(() => null);
  const side = Math.min(sides[Math.floor(STEADY_CROP_SIZE_QUANTILE * (sides.length - 1))], W, H);
  const out: CropRect[] = rects.map(() => null);
  for (let i = 0; i < rects.length; i++) {
    if (!rects[i]) continue;
    let sw = 0, sx = 0, sy = 0;
    // Walk out both ways from i until a null or ~3 sigma — never across a gap.
    for (const dir of [-1, 1]) {
      for (let j = dir < 0 ? i : i + 1; j >= 0 && j < rects.length; j += dir) {
        const r = rects[j];
        const dt = times[j] - times[i];
        if (!r || Math.abs(dt) > 3 * sigmaS) break;
        const w = sigmaS > 0 ? Math.exp(-0.5 * (dt / sigmaS) ** 2) : j === i ? 1 : 0;
        sw += w;
        sx += w * (r.x + r.width / 2) * W;
        sy += w * (r.y + r.height / 2) * H;
      }
    }
    const cx = Math.min(Math.max(sx / sw, side / 2), W - side / 2);
    const cy = Math.min(Math.max(sy / sw, side / 2), H - side / 2);
    out[i] = { x: (cx - side / 2) / W, y: (cy - side / 2) / H, width: side / W, height: side / H };
  }
  return out;
}

/**
 * A steadied track at time `t`, linearly interpolated between two real samples so
 * the pan is smooth at display rate instead of stepping at the sample rate. Next to a
 * `null` it steps exactly like `cropRectAt` — never blends into a gap.
 */
export function steadyCropAt(times: readonly number[], track: readonly CropRect[], t: number): CropRect {
  const i = sampleIndexAt(times, t);
  const a = track[i] ?? null;
  const b = track[i + 1] ?? null;
  if (!a || !b || t <= times[i]) return a;
  const k = Math.min((t - times[i]) / (times[i + 1] - times[i]), 1);
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, width: a.width, height: a.height };
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
    const idx = lookupJoint(byName, region.bone);
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
export const DANCER_COLORS = ["#F2891D", "#1E7A6F", "#C2417E", "#3F51B5"];

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
 * The source camera as a GL projection matrix (row-major, for `Matrix4.set`), for a
 * canvas of `elW` x `elH` CSS px laid exactly over a `<video>` with
 * `object-fit: contain`. A world point then lands on the same element pixel as
 * `projectToFrame` puts it in the picture — the overlay view's whole contract.
 *
 * Built from fx/fy/cx/cy directly rather than a fov, so an off-centre principal
 * point and the contain letterbox are both honoured instead of assumed away.
 */
export function sourceProjection(doc: MotionResult, elW: number, elH: number, near = 0.05, far = 100): number[] {
  const { fx, fy, cx, cy, reference_width_px: W, reference_height_px: H } = doc.camera.intrinsics;
  const s = Math.min(elW / W, elH / H); // contain: reference px -> element px
  const offX = (elW - W * s) / 2;
  const offY = (elH - H * s) / 2;
  // ndc = scale * (X / depth) + shift, and depth = -Z, so the shift goes in with -Z.
  const ax = (2 * s * fx) / elW;
  const bx = (2 * (offX + s * cx)) / elW - 1;
  const ay = (2 * s * fy) / elH;
  const by = 1 - (2 * (offY + s * cy)) / elH;
  return [
    ax, 0, -bx, 0,
    0, ay, -by, 0,
    0, 0, -(far + near) / (far - near), (-2 * far * near) / (far - near),
    0, 0, -1, 0,
  ];
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
 * A foot whose sole is within this of the fitted floor at a sample is treated as
 * standing on it. 5 cm is wider than the raw error it has to absorb (solo-01/02:
 * lowest sole sits a median 3–4 cm under the plane, p95 of the spread ±3 cm) and
 * narrower than any step that clears the floor.
 * ponytail: a hop lower than 5 cm is flattened onto the floor; per-foot contact
 * evidence in the document would lift that ceiling.
 */
export const SOLE_CONTACT_BAND_M = 0.05;

/**
 * Per-sample lift, metres along the floor normal, that puts this dancer's soles ON
 * the fitted floor. `soleGaps[k]` is the rendered mesh's lowest foot vertex above
 * the plane at sample k, before any lift (negative = under the floor).
 *
 * Why the viewer has to do this at all: the floor is fitted to foot JOINTS (the
 * lowest of ankle/subtalar/midfoot/ball, grounding.FOOT_JOINTS), and so is the
 * placement it is compared with — but the mesh sole hangs a median 3.1 cm (2.4–4.3)
 * below those joints, and per-frame pose/placement noise adds ±3 cm on top. Measured
 * on real solo-02: the lowest sole is under the floor on 97% of samples, median
 * −4.1 cm, worst −11 cm. Only the viewer has the rendered surface, so only it can
 * close that gap, and it can for every existing lesson without a recompute.
 *
 *  - contact samples (within the band): lifted so the lowest sole touches the plane;
 *  - airborne samples: the lift is interpolated from the contact samples either
 *    side, so a jump keeps its real height instead of being pulled down;
 *  - a 3-tap zero-phase average, so the body does not bob with per-frame noise;
 *  - never lower than needed to clear the floor: nothing ends up under it.
 */
export function soleLift(soleGaps: number[]): number[] {
  const n = soleGaps.length;
  const contact = soleGaps.flatMap((g, k) => (g < SOLE_CONTACT_BAND_M ? [k] : []));
  if (!contact.length) return soleGaps.map((g) => Math.max(0, -g));
  const raw = new Array<number>(n);
  let c = 0;
  for (let k = 0; k < n; k++) {
    while (c + 1 < contact.length && contact[c + 1] <= k) c++;
    const a = contact[c], b = contact[c + 1];
    if (k <= a || b === undefined) raw[k] = -soleGaps[k <= a ? a : contact[contact.length - 1]];
    else raw[k] = -soleGaps[a] + ((-soleGaps[b] + soleGaps[a]) * (k - a)) / (b - a);
  }
  return raw.map((_, k) => {
    const avg = (raw[Math.max(0, k - 1)] + raw[k] + raw[Math.min(n - 1, k + 1)]) / 3;
    return Math.max(avg, -soleGaps[k]);
  });
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
  /** Pan, as a fraction of the un-scaled ELEMENT box (letterbox included), applied before the scale. */
  tx: number;
  ty: number;
  /** True when the dancer's projected box is not wholly inside the source frame. */
  clipped: boolean;
}

export const NO_CROP: CropWindow = { zoom: 1, tx: 0, ty: 0, clipped: false };

/**
 * The source frame's width / height. From the intrinsics' reference size, the same
 * numbers `sourceProjection` letterboxes with, so a layout sized from this matches
 * the overlay; `source_video` only if those are missing.
 */
export function sourceAspect(doc: MotionResult): number {
  const { reference_width_px: W, reference_height_px: H } = doc.camera.intrinsics;
  if (W > 0 && H > 0) return W / H;
  return doc.source_video.width_px / doc.source_video.height_px;
}

/**
 * How much of an `elW` x `elH` box a frame of aspect `aspect` fills under
 * `object-fit: contain`, per axis: one of the two is 1, the other is the letterbox's
 * share. A 16:9 frame in a portrait phone panel fills all of the width and a third of
 * the height; a 9:16 one in a wide desktop panel, the reverse.
 */
export function containFit(aspect: number, elW: number, elH: number): { x: number; y: number } {
  if (!(elW > 0 && elH > 0 && aspect > 0)) return { x: 1, y: 1 };
  const box = elW / elH;
  return aspect >= box ? { x: 1, y: box / aspect } : { x: aspect / box, y: 1 };
}

/**
 * Turn a projected body rectangle into a crop window for the video element.
 *
 * `fit` is `containFit` for the element the video sits in: how much of it the frame
 * fills. `tx`/`ty` are fractions of that ELEMENT box, and `zoom` scales the element,
 * so the letterbox is part of the arithmetic — a landscape clip in a portrait panel
 * is framed by its dancer's height against the PANEL's height, which means zooming
 * past the letterbox into real, wider-than-the-panel pixels. The default (a frame
 * that fills its element) is the old behaviour exactly.
 *
 * THE HONESTY CONSTRAINT (DESIGN.md §7h). Two rules, both hard:
 *
 *  1. `zoom` is never below 1. Zooming OUT would have to invent pixels outside the
 *     frame the phone actually shot.
 *  2. On an axis where the magnified frame is wider than the panel, the visible
 *     window is clamped to stay INSIDE the source frame. When the dancer walks toward
 *     the edge the window stops at the edge and the dancer slides off centre — it
 *     never keeps panning and pads with black, and it never zooms further to hide
 *     the fact that the dancer is leaving. A dancer at the edge of frame LOOKS like a
 *     dancer at the edge of frame. On an axis where the frame is still narrower than
 *     the panel, it may slide toward the dancer but never past the panel's edge.
 *     `clipped` reports a dancer partly out of shot so the caller can say so in words.
 *
 * `MAX_CROP_ZOOM` is a second, softer limit, on how far the frame's HEIGHT is
 * magnified past filling the panel's: past ~2.5x a 1080-wide phone clip is visibly
 * upscaled, and a blurry crop implies detail the source never had.
 */
export function cropTransform(body: Rect | null, fit: { x: number; y: number } = { x: 1, y: 1 }): CropWindow {
  if (!body || body.height <= 0) return NO_CROP;
  const zoom = Math.min(Math.max(CROP_TARGET_HEIGHT / (fit.y * body.height), 1), MAX_CROP_ZOOM / fit.y);
  // `translate(t) scale(zoom)` about the element centre puts frame point p at element
  // fraction 0.5 + zoom * k * (p - 0.5) + t. Aim the dancer's centre at 0.5, then clamp:
  // |t| <= |zoom * k - 1| / 2 is rule 2 for both the wider and the narrower case.
  const pan = (c: number, k: number) => {
    const lim = Math.abs(zoom * k - 1) / 2;
    return Math.min(Math.max(-zoom * k * (c - 0.5), -lim), lim) + 0; // + 0: no -0
  };
  return {
    zoom,
    tx: pan(body.x + body.width / 2, fit.x),
    ty: pan(body.y + body.height / 2, fit.y),
    clipped: body.x < 0 || body.y < 0 || body.x + body.width > 1 || body.y + body.height > 1,
  };
}

/* -------------------------------------------------------------- view presets */

export type ViewId = "camera" | "front" | "back" | "side" | "top" | "hands" | "feet" | "overlay";

export interface ViewPreset {
  id: ViewId;
  label: string;
  /** Radians, 0 = toward the source camera, measured about the floor normal (`stageBasis`). */
  azimuth: number;
  /** Radians above the floor plane (`stageBasis`). */
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
  // Not an orbit angle: the body drawn over the video from the source camera itself
  // (`sourceProjection`). The numbers are unused; the 3D pane shows "camera" meanwhile.
  { id: "overlay", label: "on video", azimuth: 0, elevation: 0.14, distance: 1, focus: "body" },
];

/**
 * The axes the estimated views orbit in: `up` is the floor normal, `back` points from
 * the dancer toward the source camera along the floor, `right = up × back`. A preset's
 * azimuth/elevation are read in this basis (azimuth 0 = `back`, measured about `up`).
 *
 * WHY. World space IS the source camera's frame (`camera_to_world` is identity on
 * real clips), so world +Y is "up in the phone's picture", not up in the room. A
 * phone pitched up 13.6° (solo-02: normal [-0.016, 0.972, -0.235]) put every orbit
 * view on an axis 13.6° off gravity, and the side view showed the floor and the body
 * leaning by exactly that. The body and the fitted floor agree with each other (mean
 * pelvis→neck is 6° off the normal on the upright half of solo-02, vs 12° off +Y);
 * only the camera rig was tilted.
 *
 * `level` false returns the camera's own axes. The "camera" preset uses that on
 * purpose — it is the one view that is not estimated, so it stays in the source
 * camera's frame. Grounding "none" levels to the feet instead (`feetUp`), never to the
 * torso: a body-derived up is a dancer's lean, not gravity.
 */
export interface StageBasis {
  right: Vec3;
  up: Vec3;
  back: Vec3;
}

export function stageBasis(doc: MotionResult, level = true): StageBasis {
  const m = doc.camera.camera_to_world; // column-major: columns are the camera's x, y, z axes
  const camX: Vec3 = [m[0], m[1], m[2]];
  const camY: Vec3 = [m[4], m[5], m[6]];
  const camZ: Vec3 = [m[8], m[9], m[10]];
  if (!level) return { right: camX, up: camY, back: camZ };
  const plane = doc.grounding.status === "none" ? null : doc.grounding.floor_plane;
  const normal = plane ? (plane.normal as Vec3) : feetUp(doc);
  if (!normal) return { right: camX, up: camY, back: camZ };

  let up = norm(normal);
  // Up is the side of the floor the phone's picture-up points to — the dancer's head,
  // and the pipeline's own sign convention (grounding.py: normal[1] > 0), which the
  // placement in Stage3D relies on. NOT "the side the camera is on": a phone resting on
  // the floor sits within fit noise of the plane and flipped the stage upside down
  // (job_b8223229: camera 1.3 cm "below" its floor).
  if (dot(up, camY) < 0) up = [-up[0], -up[1], -up[2]];
  // The camera's +Z (toward the viewer) laid onto the floor; a straight-down camera has
  // no such direction, so its picture-down (-Y) is used instead.
  let back = reject(camZ, up);
  if (Math.hypot(...back) < 1e-3) back = reject([-camY[0], -camY[1], -camY[2]], up);
  back = norm(back);
  return { right: cross(up, back), up, back };
}

/**
 * Grounding "none": an orbit up from where the feet are, or null for the camera's own.
 *
 * A moving camera (job_a10682e7, a follow-cam) never grounds: the floor it sees tilts
 * as the phone pitches (lowest-foot plane 5.0 deg in the first half of that clip, 11.1
 * deg in the second), so no single plane passes the solver, and the orbit fell back to
 * the phone's axes — a Side view slanted by the clip's mean 8.6 deg pitch. Nothing is
 * DRAWN from this (DESIGN.md §10: no fake floor); it only levels the orbit, the way a
 * grounded clip's floor does. Least squares of each observed sample's lowest observed
 * foot height on where the dancer STANDS (root x, z) — the root, not the foot, so a kick
 * forward is not read as a slope — ridged toward level so a dancer who never travels, or
 * has no visible feet, gets the camera's axes as before.
 * On the static clips this lands within 1.5-2 deg of the solver's own floor normal.
 */
const FEET_UP_PRIOR_M = 0.1; // calibration knob: spread (std, metres) at which the fit and "level" weigh equally

function feetUp(doc: MotionResult): Vec3 | null {
  const byName = new Map(doc.joint_hierarchy.joints.map((j) => [j.name, j.index]));
  const feet = FOOT_JOINTS.map((n) => lookupJoint(byName, n)).filter((j): j is number => j !== undefined);
  const pts: Vec3[] = [];
  doc.persons.forEach((person, p) =>
    person.samples.forEach((s, i) => {
      if (!person.root_trajectory[i]?.provenance.observed) return;
      let low = Infinity;
      for (const j of feet) {
        if (s.joints[j]?.visibility === "observed") low = Math.min(low, jointWorldPosition(doc, p, i, j)[1]);
      }
      const root = person.root_trajectory[i].position;
      if (low < Infinity) pts.push([root[0], low, root[2]]);
    }),
  );
  if (pts.length < 3) return null;
  const mean = [0, 1, 2].map((k) => pts.reduce((a, v) => a + v[k], 0) / pts.length);
  let xx = 0, xz = 0, zz = 0, xy = 0, zy = 0;
  for (const v of pts) {
    const x = v[0] - mean[0], y = v[1] - mean[1], z = v[2] - mean[2];
    xx += x * x; xz += x * z; zz += z * z; xy += x * y; zy += z * y;
  }
  const ridge = pts.length * FEET_UP_PRIOR_M ** 2;
  xx += ridge; zz += ridge;
  const det = xx * zz - xz * xz;
  const a = (xy * zz - zy * xz) / det, b = (zy * xx - xy * xz) / det; // y ≈ a x + b z
  return [-a, 1, -b];
}

/** `subject + dist * (direction of azimuth/elevation in `basis`)`. */
export function orbitPosition(basis: StageBasis, subject: Vec3, azimuth: number, elevation: number, dist: number): Vec3 {
  const r = Math.sin(azimuth) * Math.cos(elevation) * dist;
  const u = Math.sin(elevation) * dist;
  const b = Math.cos(azimuth) * Math.cos(elevation) * dist;
  return [0, 1, 2].map((i) => subject[i] + basis.right[i] * r + basis.up[i] * u + basis.back[i] * b) as Vec3;
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a: Vec3): Vec3 => {
  const l = Math.hypot(...a);
  return [a[0] / l, a[1] / l, a[2] / l];
};
const reject = (a: Vec3, n: Vec3): Vec3 => {
  const k = dot(a, n);
  return [a[0] - n[0] * k, a[1] - n[1] * k, a[2] - n[2] * k];
};
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

/**
 * DESIGN.md §4: the front view is camera evidence; every other viewpoint is
 * synthesised from a tracked body and is labelled "estimated view". "camera" is the
 * only preset that is not estimated — "front" is a synthesised approximation of it
 * and is labelled as such, because the real camera is rarely exactly head-on.
 */
export function viewLabel(view: ViewId, mirrored: boolean): string {
  const preset = VIEW_PRESETS.find((p) => p.id === view)!;
  const kind = view === "camera" || view === "overlay" ? "camera view" : "estimated view";
  return mirrored ? `${preset.label} · mirrored · ${kind}` : `${preset.label} · ${kind}`;
}

export const SPEEDS = [0.25, 0.5, 0.75, 1] as const;
