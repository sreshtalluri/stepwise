/**
 * The brand mark, the one source for every drawing of it: the header lockup
 * (components/brand/Mark.tsx) and every icon file (scripts/build-brand.mjs
 * writes app/icon.svg, app/icon.png, app/apple-icon.png, public/icons/* and
 * app/opengraph-image.png from this file). Change the mark here, rerun the
 * script, and all of them follow.
 *
 * Mark A, "the dancer", round 2, line family, pose "Pop: arm lock" (owner's
 * pick): one arm locked in an L, the other dropped, hip out, one knee bent
 * out. The share image uses the secondary pose, "the wave". Both are drawn
 * with lib/countoff.ts's construction, the same as every in-page figure, one
 * notch heavier: ONE line weight at every size, from the 512 tile to the
 * 16 px favicon (owner: consistent beats heavier-at-small-sizes).
 */
import { figureParts, type Pt } from "./countoff";

export const INK = "#221E1C";
export const ACCENT = "#F2891D";
export const PAPER = "#F2EFE9";

/**
 * Line width in pose units, at every size. Round 2's favicon weight (30 on its
 * unscaled limbs, x0.88 here): the lightest that still reads as a figure at 16 px.
 */
export const MARK_STROKE = 26;

// Round 2's forward kinematics, run once (scratchpad mark-poses-r2/gen.py, limbs x0.88):
// pop-a B = pose(T=-14, h=-14, la=(-70,-30), ra=(95,180), ll=(-22,-5), rl=(50,-5)).
export const MARK_POSE: Pt[] = [[31.8,49.4],[39.4,63.5],[50.0,106.2],[14.2,78.3],[0.1,102.7],[68.7,66.2],[68.7,38.0],[32.9,148.7],[28.7,196.0],[85.1,135.6],[80.9,183.0]];
// wave B = pose(T=12, h=10, la=(-115,-120), ra=(70,62), ll=(-45,25), rl=(40,-20)).
export const WAVE_POSE: Pt[] = [[65.1,58.4],[59.1,73.3],[50.0,116.3],[32.5,66.5],[8.1,52.4],[84.5,88.0],[109.4,101.3],[17.6,148.6],[37.7,191.7],[79.4,151.3],[63.2,196.0]];

type Box = [number, number, number, number];

/** The figure's extent in pose units, strokes and head included. */
export function markBox(pose: Pt[] = MARK_POSE): Box {
  const { lines, head, r } = figureParts(pose, MARK_STROKE);
  const s = MARK_STROKE / 2;
  const pts = lines.flat();
  return [
    Math.min(...pts.map((p) => p[0] - s), head[0] - r),
    Math.min(...pts.map((p) => p[1] - s), head[1] - r),
    Math.max(...pts.map((p) => p[0] + s), head[0] + r),
    Math.max(...pts.map((p) => p[1] + s), head[1] + r),
  ];
}

const f = (n: number) => +n.toFixed(2);

/** The figure as SVG elements, pose units mapped by `k` and offset (ox, oy). */
export function markShapes(o: { pose?: Pt[]; k?: number; ox?: number; oy?: number; ink: string; head: string }): string {
  const { pose = MARK_POSE, k = 1, ox = 0, oy = 0 } = o;
  const { lines, head, r } = figureParts(pose, MARK_STROKE);
  const T = (p: Pt) => `${f(ox + p[0] * k)} ${f(oy + p[1] * k)}`;
  const paths = lines.map((pts) => `M${pts.map(T).join(" L")}`).join(" ");
  return (
    `<path d="${paths}" fill="none" stroke="${o.ink}" stroke-width="${f(MARK_STROKE * k)}" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<circle cx="${f(ox + head[0] * k)}" cy="${f(oy + head[1] * k)}" r="${f(r * k)}" fill="${o.head}"/>`
  );
}

/**
 * A square tile: the figure fitted into `fit` of the tile (a fraction), on
 * `bg` with corner radius `rx` (0 = full bleed, the OS rounds it). `floor`
 * draws round 2's faint floor line under the feet.
 */
export function markTile(o: { size: number; fit: number; bg: string; rx?: number; floor?: boolean }): string {
  const [x0, y0, x1, y1] = markBox();
  const floorY = 196 + MARK_STROKE / 2 + 8;
  const bottom = o.floor ? Math.max(y1, floorY + 5) : y1;
  const k = (o.size * o.fit) / Math.max(x1 - x0, bottom - y0);
  const ox = o.size / 2 - ((x0 + x1) / 2) * k;
  const oy = o.size / 2 - ((y0 + bottom) / 2) * k;
  const floor = o.floor
    ? `<path d="M${f(ox + 8 * k)} ${f(oy + floorY * k)} H${f(ox + 92 * k)}" stroke="${INK}" stroke-width="${f(5 * k)}" stroke-linecap="round" opacity=".35"/>`
    : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${o.size} ${o.size}" width="${o.size}" height="${o.size}">` +
    `<rect width="${o.size}" height="${o.size}" rx="${o.rx ?? 0}" fill="${o.bg}"/>${floor}` +
    markShapes({ k, ox, oy, ink: INK, head: INK }) +
    `</svg>\n`
  );
}
