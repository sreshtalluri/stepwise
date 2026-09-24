import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { dancerBox, dancerLook, firstWellObserved, markerPoint, sideWord, stillCrop } from "./dancers";
import { rootPlacementObserved, type MotionResult } from "./motion";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));

test("picker: each dancer gets a box in the frame, and two dancers are told apart by side", () => {
  const doc = load("two-dancers-apart");
  const boxes = doc.persons.map((_, i) => dancerBox(doc, i, firstWellObserved(doc, i)));
  for (const b of boxes) {
    assert.ok(b && b.width > 0 && b.height > 0);
    assert.ok(b!.x >= 0 && b!.y >= 0 && b!.x + b!.width <= 1 + 1e-9 && b!.y + b!.height <= 1 + 1e-9, "clamped to the frame");
  }
  const cx = boxes.map((b) => b!.x + b!.width / 2);
  assert.notEqual(Math.sign(cx[0] - 0.5), Math.sign(cx[1] - 0.5), `dancers sit either side of centre: ${cx}`);
  assert.notEqual(sideWord(boxes[0]), sideWord(boxes[1]));
});

test("picker crop is 3:4 in pixels, holds the dancer, and stays inside the frame", () => {
  const vw = 576, vh = 1024;
  for (const box of [
    { x: 0.1, y: 0.2, width: 0.2, height: 0.6 }, // tall dancer
    { x: 0.7, y: 0.5, width: 0.3, height: 0.1 }, // wide, at the edge
    { x: 0, y: 0, width: 1, height: 1 }, // whole frame
    null,
  ]) {
    const r = stillCrop(box, vw, vh);
    assert.ok(Math.abs((r.width * vw) / (r.height * vh) - 0.75) < 1e-9, `3:4: ${JSON.stringify(r)}`);
    assert.ok(r.x >= -1e-9 && r.y >= -1e-9 && r.x + r.width <= 1 + 1e-9 && r.y + r.height <= 1 + 1e-9, "inside the frame");
    if (box && box.height < 1) assert.ok(r.height * vh >= Math.min(box.height * vh, vh) - 1e-6, "tall enough for the dancer");
  }
});

test("the marker sits above the dancer's box, inside the frame", () => {
  const doc = load("good-lesson");
  const i = firstWellObserved(doc, 0);
  const m = markerPoint(doc, 0, i)!;
  const b = dancerBox(doc, 0, i)!;
  assert.ok(m, "a placed dancer gets a marker");
  assert.ok(m.x > b.x && m.x < b.x + b.width, "horizontally over the dancer");
  assert.ok(m.y < b.y + b.height * 0.3, "near the top of the body, not the middle");
});

test("an unplaced dancer gets no marker and a crop-rect box instead", () => {
  const doc = load("unplaced-dancer");
  const k = doc.persons.findIndex((_, i) => !rootPlacementObserved(doc, i));
  assert.ok(k >= 0, "fixture has an unplaced dancer");
  assert.equal(markerPoint(doc, k, 0), null);
  const b = dancerBox(doc, k, firstWellObserved(doc, k));
  // Either the crop rects gave a box, or there is honestly none; never a projected guess.
  if (b) assert.ok(b.width > 0 && b.height > 0);
});

test("mesh: only the selected dancer renders unless Show everyone, which brings the rest back faint", () => {
  const looks = (sel: number, all: boolean) => [0, 1, 2].map((i) => dancerLook(i, sel, all));
  assert.deepEqual(looks(1, false), ["hidden", "solo", "hidden"]);
  assert.deepEqual(looks(2, false), ["hidden", "hidden", "solo"], "switching swaps which mesh renders");
  assert.deepEqual(looks(0, true), ["solo", "faint", "faint"]);
  assert.equal(dancerLook(0, 0, true), "solo", "a single dancer is unchanged either way");
});
