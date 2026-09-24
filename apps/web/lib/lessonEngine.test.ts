import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildUpSpeed,
  chipLoop,
  countLoop,
  eightOf,
  eightsOf,
  extendAnchor,
  loadDone,
  loadLoopLength,
  loopAt,
  markDone,
  nextLoop,
  saveDone,
  saveLoopLength,
  spanDone,
  spanLabel,
  stepLoop,
  windowAt,
} from "./lessonEngine";
import { loopTimesS, mergePartWithNext, nudgeCountOne, startingStructure } from "../../../packages/navigation/src/core";

const endS = 32.47;
const base = startingStructure(endS, 0.51);
const eights = eightsOf(base);
const total = base.grid.countTotal;
const span = (startCount: number, endCount: number) => ({ startCount, endCount });

test("one chip per eight, from the structure's parts, labelled by its counts", () => {
  assert.equal(eights.length, 8);
  assert.deepEqual([eights[0].label, eights[0].startCount, eights[0].endCount], ["Counts 1–8", 1, 8]);
  assert.equal(eights.at(-1)!.endCount, total);
  const renamed = { ...base, parts: base.parts.map((p, i) => (i === 0 ? { ...p, name: "Chorus" } : p)) };
  assert.equal(eightsOf(renamed)[0].label, "Chorus");
});

test("a loop of any length starts where asked and stops at the end of the dance", () => {
  assert.deepEqual(loopAt(5, 4, total), span(5, 8));
  assert.deepEqual(loopAt(3, 2, total), span(3, 4));
  assert.deepEqual(loopAt(total - 1, 8, total), span(total - 1, total));
  assert.deepEqual(loopAt(0, 4, total), span(1, 4));
  assert.deepEqual(windowAt(7, 4, total), span(5, 8));
  assert.deepEqual(windowAt(10, 2, total), span(9, 10));
  assert.deepEqual(windowAt(12, 8, total), span(9, 16));
});

test("chip tap loops the chosen length from the chip, again = whole dance, extend = whole chips", () => {
  const one = chipLoop(null, eights[1], 8, total);
  assert.deepEqual(one, span(9, 16));
  assert.equal(chipLoop(one, eights[1], 8, total), null, "the looped chip again = whole dance");
  assert.deepEqual(chipLoop(one, eights[2], 8, total), span(17, 24), "another chip moves the loop");
  assert.deepEqual(chipLoop(null, eights[1], 4, total), span(9, 12), "four counts from the chip");
  assert.deepEqual(chipLoop(span(9, 12), eights[1], 2, total), span(9, 10), "a new length re-cuts it");
  assert.equal(chipLoop(span(9, 12), eights[1], 4, total), null);
  assert.deepEqual(chipLoop(one, eights[3], 4, total, eights[1]), span(9, 32));
  assert.deepEqual(chipLoop(one, eights[0], 2, total, eights[2]), span(1, 24), "a range dragged backwards");
  assert.equal(eightOf(eights, one)?.n, 2);
  assert.equal(eightOf(eights, span(9, 12)), null);
});

test("counts: tap loops the length from that count; shift or drag makes a range", () => {
  assert.deepEqual(countLoop(6, 4, total), span(6, 9));
  assert.deepEqual(countLoop(6, 2, total, 3), span(3, 6));
  assert.deepEqual(countLoop(3, 8, total, 6), span(3, 6), "dragged backwards");
  assert.deepEqual(countLoop(5, 8, total, 5), span(5, 5), "one count");
  assert.equal(extendAnchor(span(5, 8), 11), 5);
  assert.equal(extendAnchor(span(5, 8), 2), 8);
});

test("next and previous move by the loop length, and stay put at the ends", () => {
  assert.deepEqual(stepLoop(span(1, 4), 1, 4, 1, total), span(5, 8));
  assert.deepEqual(stepLoop(span(5, 8), 1, 4, -1, total), span(1, 4));
  assert.deepEqual(stepLoop(span(9, 10), 1, 2, 3, total), span(15, 16));
  assert.deepEqual(stepLoop(span(9, 24), 1, 4, 1, total), span(25, 28), "a range steps on from its end");
  assert.deepEqual(stepLoop(span(3, 6), 1, 4, -1, total), span(1, 4), "never before count 1");
  assert.deepEqual(stepLoop(span(1, 4), 1, 4, -1, total), span(1, 4));
  assert.deepEqual(stepLoop(span(total - 3, total), 1, 4, 1, total), span(total - 3, total));
  assert.deepEqual(stepLoop(span(9, 16), 1, 4, 0, total), span(9, 12), "delta 0 re-cuts to the length");
  assert.deepEqual(stepLoop(null, 14, 4, 0, total), span(13, 16), "from the whole dance: the window the playhead is in");
  assert.deepEqual(stepLoop(null, 14, 4, 1, total), span(17, 20));
  assert.deepEqual(nextLoop(span(1, 4), 4, total), span(5, 8));
  assert.deepEqual(nextLoop(span(9, 16), 8, total), span(17, 24));
  assert.equal(nextLoop(span(total - 7, total), 8, total), null);
  assert.equal(nextLoop(null, 4, total), null);
});

test("build up: 0.5 on the first pass, a tenth more each pass, held at 1", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 40].map(buildUpSpeed), [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1, 1]);
});

test("labels are counts, never clock time", () => {
  assert.equal(spanLabel(span(9, 16)), "Counts 9–16");
  assert.equal(spanLabel(span(3, 3)), "Count 3");
});

test("a merged part is one longer chip", () => {
  const merged = eightsOf(mergePartWithNext(base, base.parts[0].id, endS));
  assert.deepEqual([merged[0].startCount, merged[0].endCount], [1, 16]);
});

test("loop windows move with count 1 but chip ids do not", () => {
  const moved = eightsOf(nudgeCountOne(base, 1, endS));
  assert.equal(moved[0].id, eights[0].id);
  const [a0] = loopTimesS(base.grid, eights[0]);
  const [a1] = loopTimesS(nudgeCountOne(base, 1, endS).grid, moved[0]);
  assert.ok(Math.abs(a1 - a0 - 0.51) < 1e-9);
});

test("full speed ticks counts, whatever the loop length; a chip is done when all its counts are", () => {
  let done = markDone(new Set(), span(1, 4));
  assert.deepEqual([...done], [1, 2, 3, 4]);
  assert.equal(spanDone(done, eights[0]), false);
  done = markDone(done, span(5, 8));
  assert.equal(spanDone(done, eights[0]), true);
  assert.equal(spanDone(done, span(3, 6)), true);
});

test("done and loop length round-trip, v1 chip ticks carry over, and a broken store never throws", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  saveDone("abc", new Set([5, 1, 2]));
  assert.deepEqual([...loadDone("abc")], [1, 2, 5]);
  assert.equal(loadDone("other").size, 0);
  store.set("stepwise.lesson-full-speed.v1.old", JSON.stringify(["e9-16"]));
  assert.deepEqual([...loadDone("old")], [9, 10, 11, 12, 13, 14, 15, 16]);
  store.set("stepwise.lesson-full-speed.v2.bad", "{nope");
  assert.equal(loadDone("bad").size, 0);
  assert.equal(loadLoopLength("abc"), 8);
  saveLoopLength("abc", 4);
  assert.equal(loadLoopLength("abc"), 4);
  store.set("stepwise.lesson-loop-length.v1.abc", "5");
  assert.equal(loadLoopLength("abc"), 8, "only a length the control offers");
  (globalThis as any).window = { localStorage: { getItem: () => { throw new Error("private mode"); }, setItem: () => { throw new Error("quota"); } } };
  assert.equal(loadDone("abc").size, 0);
  assert.equal(loadLoopLength("abc"), 8);
  saveDone("abc", new Set([1]));
  saveLoopLength("abc", 2);
  delete (globalThis as any).window;
});
