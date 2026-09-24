import { test } from "node:test";
import assert from "node:assert/strict";
import { load, openingStructure, save } from "./structure";
import { countAtTime, countLabel, timeOfCount } from "../../../packages/navigation/src/core";

test("an untouched proposal is never restored; a learner's edit is", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    },
  };
  const structure = {
    grid: { countOneS: 1.3, secondsPerCount: 0.51, countTotal: 62 },
    parts: [{ id: "p1", name: "Part 1", startCount: 1 }],
  };
  // What older builds wrote on every open: the pipeline's first proposal, unedited.
  save("lesson-a", { structure, authored: false } as any);
  assert.equal(load("lesson-a", 33), null, "a stale proposal must not override the lesson's current one");
  save("lesson-b", { structure, authored: true } as any);
  // Restored with the counts filled in before it: the learner's 1 is still at 1.3 s.
  assert.ok(Math.abs(timeOfCount(load("lesson-b", 33)!.structure.grid, 9) - 1.3) < 1e-9);
  delete (globalThis as any).window;
});

test("the proposal's first beats are counted too, not blank before its count 1", () => {
  // job_5716ecd3…: count 1 proposed on the fourth beat of the clip.
  const [one, spc] = [2.2634673469387625, 0.6318224489795875];
  const doc = { proposed_counts: { count_one_s: one, seconds_per_count: spc, count_total: 72 } };
  const { grid } = openingStructure(doc as any, 47.6).structure;
  const beats = [3, 2, 1, 0].map((k) => one - k * spc); // 0.37 s … 2.26 s
  assert.deepEqual(beats.map((t) => countLabel(Math.floor(countAtTime(grid, t + 1e-6)))), [6, 7, 8, 1]);
  assert.ok(countAtTime(grid, 0) >= 1, "the start of the clip is inside the dance");
});
