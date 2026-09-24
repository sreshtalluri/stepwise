/**
 * The landing's count-off toy (DESIGN.md §7d, A2): a line-art figure that hits
 * one of eight poses on each count. A drawing, never a person, and the page
 * says so beside it. Ported from the approved mockup
 * (scratchpad mockups/v2/engine.js, `drawFigure`).
 */

const K = ["head", "neck", "pelvis", "lElb", "lHand", "rElb", "rHand", "lKnee", "lFoot", "rKnee", "rFoot"] as const;
type Pt = [number, number];

// One pose per count, on a 100 x 200 box with the floor at y = 196.
const POSES: Pt[][] = [
  [[50,22],[50,38],[50,100],[34,66],[30,92],[66,66],[70,92],[40,145],[34,194],[60,145],[66,194]],
  [[50,28],[50,44],[50,106],[34,62],[60,58],[66,62],[40,56],[38,150],[36,194],[62,150],[64,194]],
  [[54,22],[53,38],[52,100],[36,62],[42,84],[76,30],[94,12],[40,146],[30,194],[60,146],[62,194]],
  [[50,20],[50,36],[50,98],[30,24],[26,4],[70,24],[74,4],[42,146],[38,194],[58,146],[62,194]],
  [[50,40],[50,56],[50,118],[26,64],[8,70],[74,64],[92,70],[30,152],[28,194],[70,152],[72,194]],
  [[46,24],[47,40],[50,102],[24,40],[20,16],[70,76],[58,98],[42,148],[40,194],[62,146],[70,194]],
  [[46,24],[47,40],[48,100],[30,54],[16,40],[64,62],[74,80],[44,148],[42,194],[70,124],[92,140]],
  [[52,22],[51,38],[46,102],[30,70],[38,98],[74,28],[58,14],[36,148],[30,194],[58,150],[60,194]],
];

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
  const a = POSES[(i + 7) % 8];
  const b = POSES[i];
  const e = soft ? easeInOut(Math.min(1, frac / 0.6)) : backOut(Math.min(1, frac / 0.32));
  return a.map((p, j) => [p[0] + (b[j][0] - p[0]) * e, p[1] + (b[j][1] - p[1]) * e]);
}

/** cx = centre x, by = floor y, h = figure height, all in CSS px. */
export function drawFigure(
  ctx: CanvasRenderingContext2D,
  cx: number,
  by: number,
  h: number,
  n: number,
  frac: number,
  o: { color: string; width: number; flip: boolean; soft?: boolean; joints?: boolean },
) {
  const k = h / 200;
  const P = {} as Record<(typeof K)[number], Pt>;
  poseAt(n, frac, o.soft).forEach((p, j) => {
    P[K[j]] = [cx + (p[0] - 50) * k * (o.flip ? -1 : 1), by + (p[1] - 196) * k];
  });
  const sh = (d: number): Pt => [P.neck[0] + d * k, P.neck[1] + 4 * k];
  const hip = (d: number): Pt => [P.pelvis[0] + d * k, P.pelvis[1]];
  const line = (...pts: Pt[]) => {
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.stroke();
  };
  ctx.save();
  ctx.lineCap = ctx.lineJoin = "round";
  ctx.strokeStyle = ctx.fillStyle = o.color;
  ctx.lineWidth = o.width * k * 2;
  line(P.neck, P.pelvis);
  line(sh(-12), sh(12));
  line(hip(-8), hip(8));
  line(sh(-12), P.lElb, P.lHand);
  line(sh(12), P.rElb, P.rHand);
  line(hip(-8), P.lKnee, P.lFoot);
  line(hip(8), P.rKnee, P.rFoot);
  ctx.beginPath();
  ctx.arc(P.head[0], P.head[1], 11 * k, 0, 7);
  ctx.fill();
  if (o.joints !== false) for (const p of [P.lElb, P.lHand, P.rElb, P.rHand, P.lKnee, P.lFoot, P.rKnee, P.rFoot, P.pelvis]) {
    ctx.beginPath();
    ctx.arc(p[0], p[1], o.width * k * 1.6, 0, 7);
    ctx.fill();
  }
  ctx.restore();
}

/** Build up, as the lesson does it: 0.5x, then +0.1x each time round, up to 1x. */
export const buildStep = (speed: number) => Math.min(1, Math.round((speed + 0.1) * 10) / 10);

export const TOY_SPEEDS = [1, 0.75, 0.5] as const;
