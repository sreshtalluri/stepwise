import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { restore, save, seed } from "../lib/lessonStructure";
import { isStillProposed, proposedGrid, setCountOne, timelineEndS } from "../../../packages/navigation/src/core";
import type { MotionResult } from "../lib/motion";

/** What the viewer does: seed identically on both sides, then apply the saved copy. */
const load = (lessonId: string, doc: MotionResult, endS: number) =>
  restore(lessonId, endS) ?? seed(doc, endS);

// Minimal localStorage. The module only ever calls getItem/setItem, and a real
// DOM here would be a heavier dependency than the thing under test.
const store = new Map<string, string>();
(globalThis as { window?: unknown }).window = {
  localStorage: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  },
};

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const loadDoc = (name: string) => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8")) as MotionResult;

const withProposal = loadDoc("good-lesson");
const withoutProposal = loadDoc("failure-lesson");

test("a lesson with a beat proposal opens on the proposed grid", () => {
  store.clear();
  const endS = timelineEndS(withProposal.sample_times_s);
  const structure = load("good-lesson", withProposal, endS);

  const proposed = proposedGrid(withProposal)!;
  assert.equal(structure.grid.countOneS, proposed.countOneS);
  assert.equal(structure.grid.secondsPerCount, proposed.secondsPerCount);
  // count_total is recomputed from the same end-of-clip, so the proposal and
  // the count strip cannot disagree by one.
  assert.equal(structure.grid.countTotal, proposed.countTotal);
  assert.ok(structure.parts.length > 1, "seeded parts should still be one per eight");
});

test("a lesson with no proposal opens on the plain default grid, not a fabricated one", () => {
  store.clear();
  const endS = timelineEndS(withoutProposal.sample_times_s);
  assert.equal(proposedGrid(withoutProposal), null);
  const structure = load("failure-lesson", withoutProposal, endS);
  assert.equal(structure.grid.countOneS, 0);
  assert.equal(isStillProposed(withoutProposal, structure), false, "with no proposal, nothing can be 'still proposed'");
});

test("the label flips from proposed to authored the moment the learner moves the grid", () => {
  store.clear();
  const endS = timelineEndS(withProposal.sample_times_s);
  const seeded = load("good-lesson", withProposal, endS);
  assert.equal(isStillProposed(withProposal, seeded), true);

  // "Set 1 here" — the correction the proposal's weakest field exists to invite.
  const corrected = setCountOne(seeded, 1.25, endS);
  assert.equal(isStillProposed(withProposal, corrected), false);
});

test("authored counts survive a reload, and a JSON round-trip does not re-flag them as proposed", () => {
  store.clear();
  const endS = timelineEndS(withProposal.sample_times_s);
  const seeded = load("good-lesson", withProposal, endS);

  // Saved unchanged, then reloaded: still the proposal, not accidentally
  // "authored" by float drift through JSON.
  save("good-lesson", seeded);
  assert.equal(isStillProposed(withProposal, load("good-lesson", withProposal, endS)), true);

  const renamed = { ...seeded, parts: seeded.parts.map((p, i) => (i === 1 ? { ...p, name: "Chorus" } : p)) };
  save("good-lesson", renamed);
  const reloaded = load("good-lesson", withProposal, endS);
  assert.equal(reloaded.parts[1].name, "Chorus");

  // Scoped per lesson: another lesson in the same browser is untouched.
  const other = load("failure-lesson", withoutProposal, timelineEndS(withoutProposal.sample_times_s));
  assert.ok(other.parts.every((p) => p.name !== "Chorus"));
});
