import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildUpSpeed,
  clampSpeed,
  nextPreset,
  oneAlternates,
  SPEED_GRID,
  speedText,
  stepSpeed,
  countName,
  edgeLoop,
  loopLength,
  loopName,
  nudgeEdge,
  presetCounts,
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
  dragSnap,
  dragEdge,
  COUNT_SNAP,
  HALF_SNAP,
  FREE_SNAP,
  loadShowAnds,
  saveShowAnds,
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

test("a loop that is exactly a part names that part", () => {
  assert.equal(eightOf(eights, span(9, 16))?.n, 2);
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

test("speed: presets, 0.05 steps from 0.25 to 1.25, shown exactly", () => {
  assert.equal(stepSpeed(0.6, 1), 0.65);
  assert.equal(stepSpeed(0.65, -1), 0.6);
  assert.equal(stepSpeed(0.25, -1), 0.25, "held at the floor");
  assert.equal(stepSpeed(1.25, 1), 1.25, "held at the ceiling");
  let s = 0.25;
  for (let i = 0; i < 20; i++) s = stepSpeed(s, 1);
  assert.equal(s, 1.25, "twenty steps up land exactly, no float creep");
  assert.equal(clampSpeed(0.63), 0.65);
  assert.equal(clampSpeed(3), 1.25);
  assert.equal(clampSpeed(NaN), 1);
  assert.deepEqual([speedText(0.65), speedText(1), speedText(0.5), speedText(1.25)], ["0.65×", "1×", "0.5×", "1.25×"]);
  assert.deepEqual([1, 0.25, 0.5, 0.65, 0.75].map(nextPreset), [0.25, 0.5, 0.75, 0.75, 1]);
  assert.equal(SPEED_GRID.length, 21);
  for (let p = 0; p < 12; p++) assert.ok(SPEED_GRID.includes(buildUpSpeed(p)), "Build up stays on the grid");
});

test("try another 1: offsets from the 1 as it is now, no repeat of -1/+1, first guess first, then in order", () => {
  // job_5716ecd3…'s proposal: the tracker's order is -3, -1, -2.
  const spc = 0.6316;
  const grid = { countOneS: 2.5748, secondsPerCount: spc };
  const alts = [-3, -1, -2].map((k, i) => ({ count_one_s: 2.5748 + k * spc, shift_counts: k, confidence: 0.3 - i / 10 }));
  assert.deepEqual(oneAlternates(alts, grid).map((a) => a.by), [-3, -2], "-1 is the -1 button");
  // A later first guess still leads; the rest sort by offset.
  const mixed = [2, -3, -2].map((k) => ({ count_one_s: 2.5748 + k * spc, shift_counts: k, confidence: 0.2 }));
  assert.deepEqual(oneAlternates(mixed, grid).map((a) => a.by), [2, -3, -2]);
  // After the learner nudged count 1 one earlier, offsets are from there: -3 is now -2, -2 is -1 (dropped).
  const nudged = { ...grid, countOneS: 2.5748 - spc };
  assert.deepEqual(oneAlternates(alts, nudged).map((a) => [a.by, a.shift_counts]), [[-2, -3]]);
  // A candidate an eight away is the same 1; offsets wrap to the nearest eight (-4…3).
  assert.deepEqual(oneAlternates([{ count_one_s: 2.5748 + 6 * spc }], grid).map((a) => a.by), [-2]);
  assert.deepEqual(oneAlternates([], grid), []);
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
  const moved = eightsOf(nudgeCountOne(base, -1, endS));
  assert.equal(moved[0].id, eights[0].id);
  const [a0] = loopTimesS(base.grid, eights[0]);
  const [a1] = loopTimesS(nudgeCountOne(base, -1, endS).grid, moved[0]);
  assert.ok(Math.abs(a1 - a0 + 0.51) < 1e-9);
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
  assert.equal(loadShowAnds(), true, "a broken store shows the &");
  saveShowAnds(false);
  delete (globalThis as any).window;
});

test("the & on the count strip: on by default, remembered per device", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  assert.equal(loadShowAnds(), true);
  saveShowAnds(false);
  assert.equal(loadShowAnds(), false);
  saveShowAnds(true);
  assert.equal(loadShowAnds(), true);
  delete (globalThis as any).window;
});

test("A–B loops: a drag snaps to whole counts; Shift to the ands, Alt not at all", () => {
  assert.equal(dragSnap({}), COUNT_SNAP, "touch and a plain mouse drag: whole counts");
  assert.equal(dragSnap({ shiftKey: true }), HALF_SNAP);
  assert.equal(dragSnap({ altKey: true, shiftKey: true }), FREE_SNAP, "Alt wins");
  assert.deepEqual(edgeLoop(3.4, 7.1, total), span(3, 6), "a finger near the and of 3 lands on 3");
  assert.deepEqual(edgeLoop(3.6, 6.6, total), span(4, 6), "…and past it, on 4");
  assert.deepEqual(edgeLoop(7.1, 3.4, total), span(3, 6), "dragged backwards");
  assert.deepEqual(edgeLoop(2, 6, total), span(2, 5));
  assert.deepEqual(edgeLoop(3.4, 7.1, total, HALF_SNAP), span(3.5, 6), "Shift: 3& – 6, from the and of 3 through 6");
  assert.deepEqual(edgeLoop(3.4, 7.3, total, HALF_SNAP), span(3.5, 6.5), "Shift: 3& – 6&");
  assert.equal(edgeLoop(3, 3.4, total), null, "under one count is not a loop");
  assert.deepEqual(edgeLoop(3, 3.6, total), span(3, 3), "one count is");
  assert.equal(edgeLoop(3, 3.6, total, HALF_SNAP), null);
  assert.deepEqual(edgeLoop(-4, total + 9, total), span(1, total), "clamped to the dance");
  assert.deepEqual(edgeLoop(3.27, 7.1, total, FREE_SNAP), span(3.27, 6.1), "free, with Alt");
  // The half-count path on touch: a whole-count drag, then the ½ nudge by an end.
  assert.deepEqual(nudgeEdge(edgeLoop(3.4, 7.1, total)!, "start", 0.5, total), span(3.5, 6));
  assert.deepEqual(nudgeEdge(span(3, 6), "end", 0.5, total), span(3, 6.5));
  // A handle drag snaps only the edge in hand: the nudged 3& stays 3&.
  assert.deepEqual(dragEdge(span(3.5, 6), "end", 9.3, total), span(3.5, 8));
  assert.deepEqual(dragEdge(span(3.5, 6), "start", 1.8, total), span(2, 6));
  assert.deepEqual(dragEdge(span(3.5, 6), "end", 9.3, total, HALF_SNAP), span(3.5, 8.5));
  assert.deepEqual(dragEdge(span(3, 6), "start", 9.2, total), span(7, 8), "dragged past the end: the roles swap");
  assert.equal(loopName(span(3.5, 6)), "Loop 3& – 6");
  assert.equal(loopName(span(2, 5.5)), "Loop 2 – 5&");
  assert.equal(spanLabel(span(3.5, 6)), "Counts 3&–6");
  assert.equal(countName(3.27), "3.3");
  const [a, b] = loopTimesS(base.grid, span(3.5, 6));
  assert.ok(Math.abs(a - 2.5 * 0.51) < 1e-9 && Math.abs(b - 6 * 0.51) < 1e-9, "plays [3.5, 7) in counts");
  assert.equal(loopLength(span(3.5, 6)), 3.5);
});

test("A–B loops: each edge nudges by half a count, never below one count or out of the dance", () => {
  assert.deepEqual(nudgeEdge(span(3, 6), "start", 0.5, total), span(3.5, 6));
  assert.deepEqual(nudgeEdge(span(3.5, 6), "end", -0.5, total), span(3.5, 5.5));
  assert.deepEqual(nudgeEdge(span(1, 6), "start", -0.5, total), span(1, 6));
  assert.deepEqual(nudgeEdge(span(5, 5), "start", 0.5, total), span(5, 5));
  assert.deepEqual(nudgeEdge(span(5, 5), "end", -0.5, total), span(5, 5));
  assert.deepEqual(nudgeEdge(span(5, total), "end", 0.5, total), span(5, total));
});

test("A–B loops: next and previous step by the custom loop's own length", () => {
  const custom = span(3.5, 6); // 3.5 counts long
  assert.deepEqual(stepLoop(custom, 1, loopLength(custom), 1, total), span(7, 9.5));
  assert.deepEqual(stepLoop(span(7, 9.5), 1, 3.5, -1, total), span(3.5, 6), "and back");
  assert.deepEqual(stepLoop(custom, 1, 3.5, -1, total), span(1, 3.5), "never before count 1");
  assert.deepEqual(nextLoop(custom, 3.5, total), span(7, 9.5));
});

test("A–B loops: a half-count edge ticks only the whole counts it plays", () => {
  assert.deepEqual([...markDone(new Set(), span(3.5, 6))], [4, 5, 6]);
  assert.deepEqual([...markDone(new Set(), span(3, 5.5))], [3, 4, 5]);
  assert.deepEqual([...markDone(new Set(), span(3.5, 3.5))], []);
  assert.equal(spanDone(new Set([4, 5, 6]), span(3.5, 6)), true);
});

test("presets: 2, 4, 8, 16 or All, from here or re-cutting the loop", () => {
  assert.deepEqual(stepLoop(null, 12, presetCounts(16, total), 0, total), span(1, 16), "the 16 the playhead is in");
  assert.deepEqual(stepLoop(null, 12, presetCounts(0, total), 0, total), span(1, total), "All = the whole dance, looped");
  assert.deepEqual(stepLoop(span(9, 12), 1, presetCounts(16, total), 0, total), span(9, 24));
});
