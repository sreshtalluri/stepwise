/**
 * The drawn figure: the landing's count-off toy (DESIGN.md §7d, A2), the
 * lesson's loading screen and every state screen, and the brand mark
 * (lib/brand.ts). A drawing, never a person, and the landing says so beside it.
 *
 * One construction everywhere, the brand mark's (round 2, "line" family): one
 * thick round-capped line for the spine and the four two-segment limbs, the
 * arms from one shoulder point just under the neck and the legs from the
 * pelvis (no shoulder or hip bars), and a big round head clear of the neck.
 */

// Joint order: head, neck, pelvis, lElb, lHand, rElb, rHand, lKnee, lFoot, rKnee, rFoot.
export type Pt = [number, number];

/**
 * Limb lengths, on a 100 x 200 box with the floor at y = 196: round 2's
 * 50 / 32 / 32 / 52 / 54 (torso, upper arm, forearm, thigh, shin), times 0.88
 * so the figure and its bigger head fit the box. Long limbs and a short torso:
 * a thick line fills in short segments and small bends.
 */
const LEN = { torso: 44, upper: 28.2, fore: 28.2, thigh: 45.8, shin: 47.5 };
const SHOULDER_DROP = 5.3;

/**
 * The in-page figure's line width in pose units (of the 200-unit height). One
 * value for the toy, the loading screen and the state screens; the mark
 * (lib/brand.ts MARK_STROKE) is one notch heavier. The head's radius is the
 * line width, as in the mark.
 */
export const FIGURE_STROKE = 12;
/** Never thinner than this in CSS px, so the tiny figure beside a form error still reads. */
const MIN_LINE_PX = 2;

const unit = (a: Pt, b: Pt): Pt => {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const l = Math.hypot(dx, dy) || 1;
  return [dx / l, dy / l];
};
const step = (o: Pt, d: Pt, l: number): Pt => [o[0] + d[0] * l, o[1] + d[1] * l];

/**
 * A pose authored in the first drawing's proportions (shoulder and hip bars,
 * a long torso, short legs), re-derived for the construction above: every
 * segment keeps its angle and takes the new length. The legs and seat keep
 * their floor contact.
 */
function reproportion(p: Pt[]): Pt[] {
  const [head, neck, pelvis, lE, lH, rE, rH, lK, lF, rK, rF] = p;
  const up = unit(pelvis, neck);
  const N = step(pelvis, up, LEN.torso);
  const sh = step(N, up, -SHOULDER_DROP);
  // The upper limb aims from the new origin at the old elbow or knee (so the
  // silhouette opens out where the bars used to hold it apart); the lower
  // limb keeps its old angle.
  const limb = (origin: Pt, a: Pt, b: Pt, l1: number, l2: number): Pt[] => {
    const mid = step(origin, unit(origin, a), l1);
    return [mid, step(mid, unit(a, b), l2)];
  };
  const out: Pt[] = [
    step(N, unit(neck, head), 16), // only its direction is used (figureParts)
    N,
    pelvis,
    ...limb(sh, lE, lH, LEN.upper, LEN.fore),
    ...limb(sh, rE, rH, LEN.upper, LEN.fore),
    ...limb(pelvis, lK, lF, LEN.thigh, LEN.shin),
    ...limb(pelvis, rK, rF, LEN.thigh, LEN.shin),
  ];
  // The legs and seat carry the floor contact (a hand on the floor follows the body).
  const low = (q: Pt[]) => Math.max(...[2, 7, 8, 9, 10].map((j) => q[j][1]));
  const dy = low(p) - low(out);
  const moved = out.map(([x, y]): Pt => [x, y + dy]);
  // A foot that stood on the floor still stands on it (the new lengths can
  // leave one a few units short); only its shin stretches to get there.
  for (const j of [8, 10]) if (p[j][1] >= 190) moved[j] = [moved[j][0], p[j][1]];
  return moved;
}

const lerpPose = (a: Pt[], b: Pt[], e: number): Pt[] =>
  a.map((p, j) => [p[0] + (b[j][0] - p[0]) * e, p[1] + (b[j][1] - p[1]) * e]);

// One pose per count, authored in the first drawing's proportions.
const AUTHORED: Pt[][] = [
  [[50,22],[50,38],[50,100],[34,66],[30,92],[66,66],[70,92],[40,145],[34,194],[60,145],[66,194]],
  [[50,28],[50,44],[50,106],[34,62],[60,58],[66,62],[40,56],[38,150],[36,194],[62,150],[64,194]],
  [[54,22],[53,38],[52,100],[36,62],[42,84],[76,30],[94,12],[40,146],[30,194],[60,146],[62,194]],
  [[50,20],[50,36],[50,98],[30,24],[26,4],[70,24],[74,4],[42,146],[38,194],[58,146],[62,194]],
  [[50,40],[50,56],[50,118],[26,64],[8,70],[74,64],[92,70],[30,152],[28,194],[70,152],[72,194]],
  [[46,24],[47,40],[50,102],[24,40],[20,16],[70,76],[58,98],[42,148],[40,194],[62,146],[70,194]],
  [[46,24],[47,40],[48,100],[30,54],[16,40],[64,62],[74,80],[44,148],[42,194],[70,124],[92,140]],
  [[52,22],[51,38],[46,102],[30,70],[38,98],[74,28],[58,14],[36,148],[30,194],[58,150],[60,194]],
];
export const COUNT_POSES: Pt[][] = AUTHORED.map(reproportion);

const backOut = (x: number) => {
  const c = 1.9;
  return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2;
};

const easeInOut = (x: number) => (x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2);

/**
 * Pose for count `n` (1–8), `frac` of the way through it: snaps in over the
 * first third, or with `soft`, glides over the first 60% (the calm loading figure).
 */
export function poseAt(n: number, frac: number, soft = false): Pt[] {
  const i = (((n - 1) % 8) + 8) % 8;
  const e = soft ? easeInOut(Math.min(1, frac / 0.6)) : backOut(Math.min(1, frac / 0.32));
  return lerpPose(COUNT_POSES[(i + 7) % 8], COUNT_POSES[i], e);
}

/**
 * The state screens' poses (components/StateScreen.tsx), one pose, one meaning.
 * Each is two keyframes the figure glides between and the seconds per glide;
 * reduced motion holds the first. Authored like the counts, from the approved
 * board (scratchpad brand/figure.js), and re-derived the same way.
 */
export type StatePose = "shrug" | "sit" | "wave" | "breathe" | "look" | "sitback" | "ready";

const LEGS: Pt[] = [[44, 146], [40, 194], [56, 146], [60, 194]];
const stand = (head: Pt, neck: Pt, arms: Pt[], legs: Pt[] = LEGS): Pt[] =>
  [head, neck, [50, 100], arms[0], arms[1], arms[2], arms[3], legs[0], legs[1], legs[2], legs[3]];

const AUTHORED_STATES: Record<StatePose, [Pt[], Pt[], number]> = {
  // Nothing here: shoulders up, palms up, head tilts.
  shrug: [
    stand([50,24],[50,40],[[30,66],[20,52],[70,66],[80,52]]),
    stand([53,22],[50,37],[[30,60],[17,42],[70,60],[83,42]]),
    1.3],
  // Not yet: sits cross-legged on the floor and breathes.
  sit: [
    [[50,106],[50,122],[50,178],[28,150],[42,172],[72,150],[58,172],[22,186],[58,192],[78,186],[42,192]],
    [[51,103],[50,119],[50,178],[28,148],[42,171],[72,148],[58,171],[22,186],[58,192],[78,186],[42,192]],
    2.2],
  // Gone: one hand waves goodbye.
  wave: [
    stand([50,22],[50,38],[[37,68],[35,94],[74,34],[86,12]]),
    stand([51,22],[50,38],[[37,68],[35,94],[72,34],[66,8]]),
    0.7],
  // Slow down (a limit): arms float up and back down, one slow breath.
  breathe: [
    stand([50,22],[50,38],[[34,66],[28,92],[66,66],[72,92]]),
    stand([50,19],[50,35],[[28,18],[46,0],[72,18],[54,0]]),
    2.6],
  // Cannot reach or load: a hand shading the eyes, looking left, then right.
  look: [
    stand([46,23],[49,38],[[31,70],[42,98],[70,40],[54,21]], [[43,146],[39,194],[57,146],[61,194]]),
    stand([54,23],[51,38],[[33,72],[43,98],[78,40],[62,21]], [[44,146],[40,194],[59,146],[63,194]]),
    1.6],
  // Did not make it through: sat down on the floor, arms round the knees,
  // head dropped. Authored in the new proportions directly (see NATIVE),
  // from round 2's joint angles.
  sitback: [
    [[30.7,134.4],[20.4,146.7],[28,190],[48.5,159.2],[72.9,173.3],[49.4,149.4],[75.9,159],[57.4,154.9],[81.2,196],[62,159.4],[89.2,196]],
    [[32.3,136],[20.4,146.7],[28,190],[48.5,159.2],[72.9,173.3],[49.4,149.4],[76.5,160.5],[57.4,154.9],[81.2,196],[62,159.4],[89.2,196]],
    1.8],
  // Nothing yet: count 1, ready, barely moving.
  ready: [AUTHORED[0], stand([50,21],[50,37],[[34,65],[30,91],[66,65],[70,91]], [[40,145],[34,194],[60,145],[66,194]]), 2.2],
};

// Poses authored in the new proportions already: not re-derived.
const NATIVE: StatePose[] = ["sitback"];

export const STATE_POSES = Object.fromEntries(
  Object.entries(AUTHORED_STATES).map(([k, [a, b, s]]) =>
    [k, NATIVE.includes(k as StatePose) ? [a, b, s] : [reproportion(a), reproportion(b), s]]),
) as Record<StatePose, [Pt[], Pt[], number]>;

/** A state pose `seconds` into its idle loop: A to B and back, eased. */
export function statePoseAt(name: StatePose, seconds: number): Pt[] {
  const [a, b, s] = STATE_POSES[name];
  const ph = (seconds / s) % 2;
  return lerpPose(a, b, easeInOut(ph < 1 ? ph : 2 - ph));
}

/**
 * The figure as shapes, in pose units: round-capped polylines of width
 * `stroke`, and the head, a disc of radius `stroke` sitting clear of the
 * spine's cap along the neck's direction. lib/brand.ts draws the mark from
 * this too, so the two can only differ in weight.
 */
export function figureParts(pose: Pt[], stroke: number): { lines: Pt[][]; head: Pt; r: number } {
  const [head, neck, pelvis, lE, lH, rE, rH, lK, lF, rK, rF] = pose;
  const sh = step(neck, unit(neck, pelvis), SHOULDER_DROP);
  return {
    lines: [[neck, pelvis], [sh, lE, lH], [sh, rE, rH], [pelvis, lK, lF], [pelvis, rK, rF]],
    head: step(neck, unit(neck, head), stroke * 1.82),
    r: stroke,
  };
}

type DrawOpts = { color: string; flip: boolean; soft?: boolean };

/** cx = centre x, by = floor y, h = figure height, all in CSS px. */
export function drawFigure(
  ctx: CanvasRenderingContext2D,
  cx: number,
  by: number,
  h: number,
  n: number,
  frac: number,
  o: DrawOpts,
) {
  drawPose(ctx, cx, by, h, poseAt(n, frac, o.soft), o);
}

/** drawFigure for any 11-point pose (a count, or a state pose). */
export function drawPose(ctx: CanvasRenderingContext2D, cx: number, by: number, h: number, pose: Pt[], o: DrawOpts) {
  const k = h / 200;
  const px = ([x, y]: Pt): Pt => [cx + (x - 50) * k * (o.flip ? -1 : 1), by + (y - 196) * k];
  const width = Math.max(MIN_LINE_PX, FIGURE_STROKE * k);
  const { lines, head } = figureParts(pose, width / k);
  ctx.save();
  ctx.lineCap = ctx.lineJoin = "round";
  ctx.strokeStyle = ctx.fillStyle = o.color;
  ctx.lineWidth = width;
  for (const pts of lines) {
    ctx.beginPath();
    pts.map(px).forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.stroke();
  }
  const [hx, hy] = px(head);
  ctx.beginPath();
  ctx.arc(hx, hy, width, 0, 7);
  ctx.fill();
  ctx.restore();
}

/** Build up, as the lesson does it: 0.5x, then +0.1x each time round, up to 1x. */
export const buildStep = (speed: number) => Math.min(1, Math.round((speed + 0.1) * 10) / 10);

export const TOY_SPEEDS = [1, 0.75, 0.5] as const;
