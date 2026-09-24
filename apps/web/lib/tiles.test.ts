/**
 * The desktop's tile layout (lib/tiles.ts): count + space → grid. The sizes are the
 * panels' measured content box with 2+ views at 1600×900, 1280×800, 1024×700 and a
 * 768×1024 tablet. Run: npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { tileGrid } from "./tiles";

const ANGLE = 3 / 4;
const TALL = 9 / 16;
const WIDE = 16 / 9;
const shape = (g: ReturnType<typeof tileGrid>) => `${g.cols.length}x${g.rows.length}`;

test("one view fills the space", () => {
  assert.equal(shape(tileGrid([TALL], 1553, 628)), "1x1");
});

test("a wide desktop: 2 and 3 go across, 4 is a 2x2, never four slivers", () => {
  for (const [w, h] of [[1553, 628], [1233, 528], [977, 428]]) {
    assert.equal(shape(tileGrid([TALL, ANGLE], w, h)), "2x1", `2 @${w}`);
    assert.equal(shape(tileGrid([TALL, ANGLE, ANGLE], w, h)), "3x1", `3 @${w}`);
    assert.equal(shape(tileGrid([TALL, ANGLE, ANGLE, ANGLE], w, h)), "2x2", `4 @${w}`);
    assert.equal(shape(tileGrid([ANGLE, ANGLE, ANGLE, ANGLE], w, h)), "2x2", `4 angles @${w}`);
  }
});

test("a portrait tablet: 2 stack, 3 is one big and two small, 4 is a 2x2", () => {
  assert.equal(shape(tileGrid([TALL, ANGLE], 736, 752)), "1x2");
  const three = tileGrid([TALL, ANGLE, ANGLE], 736, 752);
  assert.equal(shape(three), "2x2");
  assert.equal(Math.max(three.areas[0][2], three.areas[0][3]), 2, "the first is the big one");
  assert.equal(shape(tileGrid([TALL, ANGLE, ANGLE, ANGLE], 736, 752)), "2x2");
});

test("a 16:9 video gets the wider column; with two angles it is the big one on the left", () => {
  const two = tileGrid([WIDE, ANGLE], 1553, 628);
  assert.equal(shape(two), "2x1");
  assert.ok(two.cols[0] > two.cols[1]);
  const three = tileGrid([WIDE, ANGLE, ANGLE], 1553, 628);
  assert.deepEqual(three.areas[0], [1, 1, 1, 2]);
});

test("no tile is a sliver when another layout exists", () => {
  for (let n = 1; n <= 4; n++) {
    for (const [w, h] of [[1553, 628], [1233, 528], [977, 428], [736, 752], [520, 330]]) {
      const aspects = [TALL, ...Array(n - 1).fill(ANGLE)];
      const g = tileGrid(aspects, w, h);
      assert.equal(g.areas.length, n);
      const free = (fr: number[], len: number) => fr.map((f) => ((len - 6 * (fr.length - 1)) * f) / fr.reduce((a, b) => a + b));
      const cw = free(g.cols, w);
      g.areas.forEach(([c, , cs], i) => {
        const width = cw.slice(c - 1, c - 1 + cs).reduce((a, b) => a + b, 0);
        assert.ok(width > 150, `n=${n} @${w}x${h}: tile ${i} is ${width | 0}px wide`);
      });
    }
  }
});
