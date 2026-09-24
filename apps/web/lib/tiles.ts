/**
 * How the desktop lays out the views that are on: which grid, given how many there
 * are, the shape each wants, and the shape of the space. The rule, in words:
 *
 *   - every arrangement of the tiles is tried: one row, one column, a 2×2, and for
 *     three a big one plus two small (left, or on top);
 *   - one where a tile would be much narrower than what it shows (a sliver) is out,
 *     unless nothing else is left — letterboxing a wide cell is fine, a thin one is not;
 *   - of the rest, the one that shows the most picture wins (each tile's content,
 *     fitted `contain`-style into its cell, summed).
 *
 * So at a 2:1 desktop: 2 and 3 go across, 4 is a 2×2; on a portrait tablet 2 stack
 * and 3 is one big and two small. A single row sizes its columns to each tile's
 * shape (a 16:9 video gets more width than a 3:4 angle), like a justified gallery.
 */

/** A cell narrower than this share of its content's shape (or of a square, for wide
 * content — a 16:9 video letterboxed top and bottom in a squarish cell is fine) is a
 * sliver. 0.9: four 3:4 angles in a row at 1600×900 (cells ≈ 0.62) are out — the
 * "four thin slivers" this replaced — while three in a row at 1024×700 still fit. */
const SLIVER = 0.9;

export type TileGrid = {
  /** grid-template-columns / -rows, as `fr` weights. */
  cols: number[];
  rows: number[];
  /** Per tile, in order: [column, row, column span, row span], 1-based like CSS. */
  areas: [number, number, number, number][];
};

type Cand = TileGrid;

const sum = (a: number[]) => a.reduce((s, x) => s + x, 0);

function candidates(aspects: number[]): Cand[] {
  const n = aspects.length;
  const one = { cols: [1], rows: [1], areas: [[1, 1, 1, 1]] } as Cand;
  if (n <= 1) return [one];
  const out: Cand[] = [
    // One row, columns weighted by each tile's shape; one column, rows by the inverse.
    { cols: aspects, rows: [1], areas: aspects.map((_, i) => [i + 1, 1, 1, 1]) },
    { cols: [1], rows: aspects.map((a) => 1 / a), areas: aspects.map((_, i) => [1, i + 1, 1, 1]) },
    // One row, equal columns (the old behaviour): kept so it can still win when it fits.
    { cols: aspects.map(() => 1), rows: [1], areas: aspects.map((_, i) => [i + 1, 1, 1, 1]) },
  ];
  if (n === 3) {
    out.push({ cols: [1, 1], rows: [1, 1], areas: [[1, 1, 1, 2], [2, 1, 1, 1], [2, 2, 1, 1]] });
    out.push({ cols: [1, 1], rows: [1, 1], areas: [[1, 1, 2, 1], [1, 2, 1, 1], [2, 2, 1, 1]] });
  }
  if (n === 4) out.push({ cols: [1, 1], rows: [1, 1], areas: [[1, 1, 1, 1], [2, 1, 1, 1], [1, 2, 1, 1], [2, 2, 1, 1]] });
  return out;
}

/** Each tile's cell size in px for a candidate in a `w`×`h` box with `gap` between tracks. */
function cells(c: Cand, w: number, h: number, gap: number): [number, number][] {
  const track = (fr: number[], len: number) => {
    const free = Math.max(0, len - gap * (fr.length - 1));
    return fr.map((f) => (free * f) / sum(fr));
  };
  const cw = track(c.cols, w);
  const rh = track(c.rows, h);
  const span = (t: number[], start: number, n: number) => sum(t.slice(start - 1, start - 1 + n)) + gap * (n - 1);
  return c.areas.map(([col, row, cs, rs]) => [span(cw, col, cs), span(rh, row, rs)]);
}

/**
 * The grid for tiles wanting `aspects` (width / height each: a 9:16 video 0.5625, a
 * 3D angle 3/4, …) in a `w`×`h` px box.
 */
export function tileGrid(aspects: number[], w: number, h: number, gap = 6): TileGrid {
  let best: { c: Cand; ok: boolean; score: number } | null = null;
  for (const c of candidates(aspects)) {
    const cs = cells(c, w, h, gap);
    let score = 0;
    let ok = true;
    cs.forEach(([cw, ch], i) => {
      const a = aspects[i];
      if (ch <= 0 || cw / ch < Math.min(a, 1) * SLIVER) ok = false;
      const fw = Math.min(cw, ch * a);
      score += (fw * fw) / a;
    });
    if (!best || (ok && !best.ok) || (ok === best.ok && score > best.score)) best = { c, ok, score };
  }
  return best!.c;
}
