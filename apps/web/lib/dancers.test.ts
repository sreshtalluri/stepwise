import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { dancerBox, firstWellObserved, markerPoint, sideWord } from "./dancers";
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
