import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isComplete,
  lessonUnits,
  loadLearned,
  nextRound,
  rampSpeeds,
  roundAt,
  saveLearned,
  schedule,
  stepProgress,
  stepStart,
  stepOf,
  SLOW_LOOPS,
} from "./lessonEngine";
import { mergePartWithNext, nudgeCountOne, startingStructure, loopTimesS } from "../../../packages/navigation/src/core";

test("build-up ramps 0.5 → 1 by a tenth, with no float dust", () => {
  assert.deepEqual(rampSpeeds(), [0.5, 0.6, 0.7, 0.8, 0.9, 1]);
  assert.deepEqual(rampSpeeds(0.6, 1, 0.2), [0.6, 0.8, 1]);
});

test("an 8-count is watch, slow ×3, the ramp, your turn, then full speed", () => {
  const r = schedule("eight");
  assert.deepEqual(r.map((x) => x.step), ["watch", "slow", "slow", "slow", "build", "build", "build", "build", "build", "build", "build", "full", "full"]);
  assert.deepEqual(r.filter((x) => x.step === "build" && !x.yourTurn).map((x) => x.speed), rampSpeeds());
  const turn = r.filter((x) => x.yourTurn);
  assert.equal(turn.length, 1);
  assert.equal(turn[0].speed, 1, "your turn is at full speed, after the ramp reaches it");
  assert.equal(r[0].speed, 1);
  assert.equal(stepProgress(r, 0, "slow").total, SLOW_LOOPS);
});

test("a join skips watch", () => {
  assert.equal(schedule("join")[0].step, "slow");
  assert.ok(schedule("join").length < schedule("eight").length);
});

test("rounds advance once per wrap and clamp at complete", () => {
  const r = schedule("eight");
  let i = 0;
  for (let k = 0; k < 100; k++) i = nextRound(r, i);
  assert.equal(i, r.length);
  assert.ok(isComplete(r, i));
  assert.equal(stepOf(r, i), "done");
  assert.equal(roundAt(r, i).speed, 1, "complete plays at full speed");
  assert.equal(stepOf(r, stepStart(r, "build")), "build");
  assert.equal(roundAt(r, stepStart(r, "build")).speed, 0.5);
});

test("step pips: done counts rounds already played", () => {
  const r = schedule("eight");
  const slow = stepStart(r, "slow");
  assert.deepEqual(stepProgress(r, slow + 2, "slow"), { done: 2, total: 3 });
  assert.deepEqual(stepProgress(r, stepStart(r, "full"), "slow"), { done: 3, total: 3 });
  assert.deepEqual(stepProgress(r, 0, "full"), { done: 0, total: 2 });
});

const endS = 32.47;
const base = startingStructure(endS, 0.51);

test("units: every eight, a join after every second, the last join is the whole dance", () => {
  const u = lessonUnits(base);
  const eights = u.filter((x) => x.kind === "eight");
  assert.equal(eights.length, 8);
  assert.equal(eights[0].label, "8-count 1");
  assert.deepEqual([eights[0].startCount, eights[0].endCount], [1, 8]);
  const joins = u.filter((x) => x.kind === "join");
  assert.deepEqual(joins.map((j) => j.label), ["Together 1 to 2", "Together 1 to 4", "Together 1 to 6", "Whole dance"]);
  assert.ok(joins.every((j) => j.startCount === 1));
  assert.equal(joins.at(-1)!.endCount, base.grid.countTotal);
  assert.equal(u[2].kind, "join", "the join follows its pair");
});

test("a merged part says its counts, not '8-count'", () => {
  const merged = mergePartWithNext(base, base.parts[0].id, endS);
  assert.equal(lessonUnits(merged)[0].label, "Counts 1–16");
});

test("loop windows move with count 1 but unit ids do not", () => {
  const before = lessonUnits(base)[0];
  const moved = nudgeCountOne(base, 1, endS);
  const after = lessonUnits(moved)[0];
  assert.equal(after.id, before.id);
  const [a0] = loopTimesS(base.grid, before);
  const [a1] = loopTimesS(moved.grid, after);
  assert.ok(Math.abs(a1 - a0 - 0.51) < 1e-9);
});

test("learned state round-trips, and a broken store never throws", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  saveLearned("abc", new Set(["e1-8", "j1-16"]));
  assert.deepEqual([...loadLearned("abc")].sort(), ["e1-8", "j1-16"]);
  assert.equal(loadLearned("other").size, 0);
  store.set("stepwise.lesson-learned.v1.bad", "{nope");
  assert.equal(loadLearned("bad").size, 0);
  (globalThis as any).window = { localStorage: { getItem: () => { throw new Error("private mode"); }, setItem: () => { throw new Error("quota"); } } };
  assert.equal(loadLearned("abc").size, 0);
  saveLearned("abc", new Set(["x"]));
  delete (globalThis as any).window;
});
