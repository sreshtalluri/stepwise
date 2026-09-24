import { test } from "node:test";
import assert from "node:assert/strict";
import { load, save } from "./structure";

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
  assert.equal(load("lesson-b", 33)?.structure.grid.countOneS, 1.3);
  delete (globalThis as any).window;
});
