import { test } from "node:test";
import assert from "node:assert/strict";
import { buildUpSpeed, chipLoop, eightOf, eightsOf, loadDone, nextEight, saveDone, spanLabel } from "./lessonEngine";
import { loopTimesS, mergePartWithNext, nudgeCountOne, startingStructure } from "../../../packages/navigation/src/core";

const endS = 32.47;
const base = startingStructure(endS, 0.51);
const eights = eightsOf(base);

test("one chip per eight, from the structure's parts", () => {
  assert.equal(eights.length, 8);
  assert.deepEqual([eights[0].label, eights[0].startCount, eights[0].endCount], ["8-count 1", 1, 8]);
  assert.equal(eights.at(-1)!.endCount, base.grid.countTotal);
  const renamed = { ...base, parts: base.parts.map((p, i) => (i === 0 ? { ...p, name: "Chorus" } : p)) };
  assert.equal(eightsOf(renamed)[0].label, "Chorus");
});

test("tap loops an eight, tapping it again plays the whole dance, extend loops a range", () => {
  const one = chipLoop(null, eights[1]);
  assert.deepEqual(one, { startCount: 9, endCount: 16 });
  assert.equal(chipLoop(one, eights[1]), null, "the looped chip again = whole dance");
  assert.deepEqual(chipLoop(one, eights[2]), { startCount: 17, endCount: 24 }, "another chip moves the loop");
  assert.deepEqual(chipLoop(one, eights[3], eights[1]), { startCount: 9, endCount: 32 });
  assert.deepEqual(chipLoop(one, eights[0], eights[2]), { startCount: 1, endCount: 24 }, "a range dragged backwards");
  assert.equal(eightOf(eights, one)?.n, 2);
  assert.equal(eightOf(eights, { startCount: 9, endCount: 32 }), null);
});

test("next is the eight after the loop, and nothing after the last", () => {
  assert.equal(nextEight(eights, { startCount: 9, endCount: 16 })?.n, 3);
  assert.equal(nextEight(eights, { startCount: 1, endCount: 24 })?.n, 4);
  assert.equal(nextEight(eights, { startCount: eights.at(-1)!.startCount, endCount: eights.at(-1)!.endCount }), null);
  assert.equal(nextEight(eights, null), null);
});

test("build up: 0.5 on the first pass, a tenth more each pass, held at 1", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 40].map(buildUpSpeed), [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1, 1]);
});

test("labels are counts, never clock time", () => {
  assert.equal(spanLabel({ startCount: 9, endCount: 16 }), "Counts 9–16");
  assert.equal(spanLabel({ startCount: 3, endCount: 3 }), "Count 3");
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

test("done-at-full-speed round-trips, and a broken store never throws", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  saveDone("abc", new Set(["e1-8", "e9-16"]));
  assert.deepEqual([...loadDone("abc")].sort(), ["e1-8", "e9-16"]);
  assert.equal(loadDone("other").size, 0);
  store.set("stepwise.lesson-full-speed.v1.bad", "{nope");
  assert.equal(loadDone("bad").size, 0);
  (globalThis as any).window = { localStorage: { getItem: () => { throw new Error("private mode"); }, setItem: () => { throw new Error("quota"); } } };
  assert.equal(loadDone("abc").size, 0);
  saveDone("abc", new Set(["x"]));
  delete (globalThis as any).window;
});
