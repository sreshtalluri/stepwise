import { test } from "node:test";
import assert from "node:assert/strict";
import { barOptions, countAt, leadInStart, optionOf } from "./ownerCount";

test("options are the first bar of the grid, whatever bar the detector picked", () => {
  // bhangra (scratch labels): detector 2.575 s, one count 0.6316 s -> A 0.048 s.
  assert.deepEqual(barOptions(2.575, 0.6316039829302987), [0.049, 0.68, 1.312, 1.943]);
  assert.deepEqual(barOptions(1.439, 0.4), [0.239, 0.639, 1.039, 1.439]);
  assert.deepEqual(barOptions(0, 0.5), [0, 0.5, 1, 1.5]);
});

test("optionOf finds the same beat of the bar in any bar", () => {
  assert.equal(optionOf(1.439, 1.439, 0.4), 3);
  assert.equal(optionOf(1.439 + 0.4, 1.439, 0.4), 0);
  assert.equal(optionOf(1.439 + 8 * 0.4, 1.439, 0.4), 3);
  assert.equal(optionOf(0.239, 1.439, 0.4), 0);
});

test("counts run 1-8 from the origin, 5 6 7 8 during the lead-in", () => {
  assert.deepEqual(countAt(1.0, 1.0, 0.5), { beat: 0, count: 1 });
  assert.deepEqual(countAt(1.49, 1.0, 0.5), { beat: 0, count: 1 });
  assert.deepEqual(countAt(4.5, 1.0, 0.5), { beat: 7, count: 8 });
  assert.deepEqual(countAt(5.0, 1.0, 0.5), { beat: 8, count: 1 });
  assert.equal(countAt(0.0, 1.0, 0.5).count, 7);
  assert.equal(leadInStart(1.0, 0.5), 0);
  assert.equal(leadInStart(3.0, 0.5), 1);
});
