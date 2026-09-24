import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  advance,
  countAtTime,
  currentCount,
  deletePart,
  eightStartCount,
  gridFromTaps,
  loopLabel,
  loopTimesS,
  mergePartWithNext,
  nearestCountBoundary,
  normalizeStructure,
  partLabel,
  partRangeAtCount,
  partRanges,
  retempo,
  sampleIndexAt,
  setCountOne,
  nudgeCountOne,
  tapOnOne,
  splitPartAt,
  startingStructure,
  timeOfCount,
  timelineEndS,
} from "../src/core.js";
import type { LessonStructure } from "../src/core.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = path.join(here, "..", "..", "motion-contract", "fixtures");
const load = (name: string) => JSON.parse(readFileSync(path.join(fixtures, name), "utf-8"));

const good = load("good-lesson.json");
const failure = load("failure-lesson.json");

// ------------------------------------------------------------------ timeline

test("the clip ends at the last sample slot, not at duration_s", () => {
  // The contract says sample_times_s is authoritative and duration_s may differ
  // by rounding. 210 samples at 15fps end at 13.933…, while duration_s is 14.
  assert.equal(timelineEndS(good.sample_times_s), 13.933333);
  assert.notEqual(timelineEndS(good.sample_times_s), good.source_video.duration_s);
});

test("sampleIndexAt finds the slot in effect, never index * (1/fps)", () => {
  const times: number[] = good.sample_times_s;
  assert.equal(sampleIndexAt(times, -1), 0);
  assert.equal(sampleIndexAt(times, 0), 0);
  assert.equal(sampleIndexAt(times, 1e6), times.length - 1);
  for (const i of [1, 7, 42, 137, times.length - 1]) {
    assert.equal(sampleIndexAt(times, times[i]), i, `exact hit on sample ${i}`);
    assert.equal(sampleIndexAt(times, times[i] + 0.001), i, `just after sample ${i}`);
    assert.equal(sampleIndexAt(times, times[i] - 0.001), i - 1, `just before sample ${i}`);
  }
});

test("sampleIndexAt survives a non-uniform timeline (the reason the field exists)", () => {
  // A dropped frame: the gap between slots 2 and 3 is four frame periods wide.
  const dropped = [0, 0.0667, 0.1333, 0.4, 0.4667, 0.5333];
  assert.equal(sampleIndexAt(dropped, 0.3), 2, "inside the gap, the last real sample still holds");
  assert.equal(sampleIndexAt(dropped, 0.4), 3);
  // Index arithmetic would have claimed slot 4 at t=0.2667 — which does not exist.
  assert.notEqual(sampleIndexAt(dropped, 0.2667), Math.round(0.2667 * 15));
});

test("seeking across the failure fixture's dropout lands on real slots", () => {
  const times: number[] = failure.sample_times_s;
  // The left arm is occluded from sample 30 to 50 and returns at 51.
  assert.equal(sampleIndexAt(times, times[30]), 30);
  assert.equal(sampleIndexAt(times, times[51]), 51);
  assert.equal(failure.persons[0].samples.length, times.length, "per-sample arrays match N");
});

// -------------------------------------------------------------- counts, parts

const endS = timelineEndS(good.sample_times_s);
const base: LessonStructure = startingStructure(endS, 14 / 30); // ~30 counts over the clip

test("a starting structure covers the clip in eights", () => {
  assert.equal(base.grid.countTotal, 30);
  assert.deepEqual(base.parts.map((p) => p.startCount), [1, 9, 17, 25]);
  assert.deepEqual(partRanges(base).map((r) => [r.startCount, r.endCount]), [
    [1, 8],
    [9, 16],
    [17, 24],
    [25, 30],
  ]);
});

test("count <-> time round-trips, and counts display 1-8 inside their eight", () => {
  assert.equal(currentCount(base.grid, timeOfCount(base.grid, 9)), 9);
  assert.equal(currentCount(base.grid, timeOfCount(base.grid, 9) + 0.01), 9);
  assert.equal(currentCount(base.grid, timeOfCount(base.grid, 9) - 0.01), 8);
  assert.equal(eightStartCount(9), 9);
  assert.equal(eightStartCount(16), 9);
  assert.equal(eightStartCount(17), 17);
  assert.ok(Math.abs(countAtTime(base.grid, timeOfCount(base.grid, 4.5)) - 4.5) < 1e-9);
});

test("sections are named semantically, never as timestamps", () => {
  const label = partLabel(partRangeAtCount(base, 12));
  assert.equal(label, "Part 2 · counts 9\u201316");
  assert.ok(!/\d:\d\d/.test(label), "no clock time in a section name");
});

test("loop edges are count boundaries", () => {
  const [a, b] = loopTimesS(base.grid, { startCount: 9, endCount: 16 });
  assert.equal(a, timeOfCount(base.grid, 9));
  assert.equal(b, timeOfCount(base.grid, 17), "the loop ends on the leading edge of count 17");
  // Dragging a handle to an arbitrary second always lands on a boundary.
  const dragged = nearestCountBoundary(base.grid, timeOfCount(base.grid, 12) + 0.2);
  assert.equal(dragged, 12);
  assert.equal(nearestCountBoundary(base.grid, -99), 1);
  assert.equal(nearestCountBoundary(base.grid, 1e6), base.grid.countTotal + 1);
});

test("the loop control's label always names the loop it will actually play", () => {
  assert.equal(loopLabel(base, { startCount: 9, endCount: 16 }), "Loop part 2");
  // Once a handle is dragged off the part boundary, "part 2" would be a lie.
  assert.equal(loopLabel(base, { startCount: 9, endCount: 14 }), "Loop counts 9–14");
  assert.equal(loopLabel(base, { startCount: 11, endCount: 11 }), "Loop count 11");
});

// ------------------------------------------------------------------ authoring

test("split, merge and delete keep parts a gapless partition of the counts", () => {
  const assertPartition = (s: LessonStructure, why: string) => {
    const ranges = partRanges(s);
    assert.equal(ranges[0].startCount, 1, `${why}: starts at count 1`);
    assert.equal(ranges[ranges.length - 1].endCount, s.grid.countTotal, `${why}: ends at the last count`);
    ranges.slice(1).forEach((r, i) => assert.equal(r.startCount, ranges[i].endCount + 1, `${why}: no gap`));
  };

  const split = splitPartAt(base, 5, endS);
  assert.deepEqual(split.parts.map((p) => p.startCount), [1, 5, 9, 17, 25]);
  assert.deepEqual(split.parts.map((p) => p.name), ["Part 1", "Part 2", "Part 3", "Part 4", "Part 5"]);
  assertPartition(split, "after split");

  assert.equal(splitPartAt(base, 9, endS), base, "splitting on an existing boundary is a no-op");
  assert.equal(splitPartAt(base, 1, endS), base, "count 1 is always a boundary already");

  const merged = mergePartWithNext(split, split.parts[1].id, endS);
  assert.deepEqual(merged.parts.map((p) => p.startCount), [1, 5, 17, 25]);
  assertPartition(merged, "after merge");

  const removed = deletePart(base, base.parts[1].id, endS);
  assert.deepEqual(removed.parts.map((p) => p.startCount), [1, 17, 25]);
  assert.equal(partRangeAtCount(removed, 12).part.name, "Part 1", "orphaned counts join the previous part");
  assertPartition(removed, "after delete");

  const firstRemoved = deletePart(base, base.parts[0].id, endS);
  assert.equal(firstRemoved.parts[0].startCount, 1, "deleting the first part promotes the next one to count 1");
  assertPartition(firstRemoved, "after deleting the first part");

  const single: LessonStructure = { grid: base.grid, parts: [base.parts[0]] };
  assert.equal(deletePart(single, base.parts[0].id, endS), single, "the last part cannot be deleted");
});

test("a custom part name survives renumbering, a default one does not", () => {
  const named: LessonStructure = normalizeStructure(
    { grid: base.grid, parts: [{ ...base.parts[0], name: "Chorus" }, base.parts[1], base.parts[2], base.parts[3]] },
    endS,
  );
  assert.deepEqual(named.parts.map((p) => p.name), ["Chorus", "Part 2", "Part 3", "Part 4"]);
});

test("'set 1 here' re-anchors without disturbing the spacing", () => {
  const moved = setCountOne(base, 1.2, endS);
  assert.equal(moved.grid.secondsPerCount, base.grid.secondsPerCount);
  assert.equal(moved.grid.countOneS, 1.2);
  assert.equal(timeOfCount(moved.grid, 1), 1.2);
  assert.ok(moved.grid.countTotal < base.grid.countTotal, "a later count 1 leaves room for fewer counts");
});

test("half and double keep every part boundary at the same moment in time", () => {
  const timeOfBoundaries = (s: LessonStructure) => s.parts.map((p) => timeOfCount(s.grid, p.startCount));

  const doubled = retempo(base, "double", endS);
  assert.equal(doubled.grid.secondsPerCount, base.grid.secondsPerCount / 2);
  assert.deepEqual(doubled.parts.map((p) => p.startCount), [1, 17, 33, 49]);
  timeOfBoundaries(doubled).forEach((t, i) =>
    assert.ok(Math.abs(t - timeOfBoundaries(base)[i]) < 1e-9, `boundary ${i} stayed put`),
  );

  const back = retempo(doubled, "half", endS);
  assert.ok(Math.abs(back.grid.secondsPerCount - base.grid.secondsPerCount) < 1e-9);
  assert.deepEqual(back.parts.map((p) => p.startCount), base.parts.map((p) => p.startCount));
});

test("tap-in needs two taps and averages the gaps", () => {
  assert.equal(gridFromTaps(base, [1.0], endS), null);
  assert.equal(gridFromTaps(base, [1.0, 1.0], endS), null, "zero spacing is not a tempo");
  const tapped = gridFromTaps(base, [1.0, 1.55, 2.0, 2.5], endS)!;
  assert.equal(tapped.grid.countOneS, 1.0);
  assert.ok(Math.abs(tapped.grid.secondsPerCount - 0.5) < 1e-9, "(2.5 - 1.0) / 3");
});

test("−1 / +1 count moves count 1 by one spacing and keeps the parts on their counts", () => {
  const one = setCountOne(base, 2.0, endS);
  const spc = one.grid.secondsPerCount;
  const later = nudgeCountOne(one, 1, endS);
  assert.ok(Math.abs(later.grid.countOneS - (2.0 + spc)) < 1e-9);
  assert.equal(later.grid.secondsPerCount, spc);
  assert.deepEqual(later.parts.map((p) => p.startCount), one.parts.map((p) => p.startCount).filter((c) => c <= later.grid.countTotal));
  const earlier = nudgeCountOne(one, -1, endS);
  assert.ok(Math.abs(earlier.grid.countOneS - (2.0 - spc)) < 1e-9);
});

test("count 1 never goes before the clip — one count earlier wraps to seven later", () => {
  const atStart = setCountOne(base, 0.1, endS);
  const spc = atStart.grid.secondsPerCount;
  const nudged = nudgeCountOne(atStart, -1, endS);
  assert.ok(Math.abs(nudged.grid.countOneS - (0.1 + 7 * spc)) < 1e-9);
});

test("tap on 1 snaps to the nearest beat and moves count 1 at most four counts", () => {
  const one = setCountOne(base, 1.0, endS);
  const spc = one.grid.secondsPerCount;
  // A late tap near the beat two counts after the old count 1 of the third eight.
  const tapped = tapOnOne(one, 1.0 + (16 + 2) * spc + 0.12, endS);
  assert.ok(Math.abs(tapped.grid.countOneS - (1.0 + 2 * spc)) < 1e-9, `got ${tapped.grid.countOneS}`);
  // Three counts before a 1 is the same as "the 1 is three counts earlier".
  const early = tapOnOne(one, 1.0 + (24 - 3) * spc, endS);
  assert.ok(Math.abs(early.grid.countOneS - (1.0 + 5 * spc)) < 1e-9, "wrapped forward, not before the clip");
  // Tapping on a beat that is already a 1 changes nothing.
  const same = tapOnOne(one, 1.0 + 8 * spc - 0.05, endS);
  assert.ok(Math.abs(same.grid.countOneS - 1.0) < 1e-9);
});

// ------------------------------------------------------------------- playback

test("loop mode repeats silently and never leaves the loop", () => {
  const loop = { startCount: 9, endCount: 16 };
  const [a, b] = loopTimesS(base.grid, loop);
  const o = { mode: "loop" as const, grid: base.grid, loop, endS };

  assert.deepEqual(advance(a, 0.1, o), { timeS: a + 0.1, playing: true });
  const wrapped = advance(b - 0.02, 0.05, o);
  assert.ok(Math.abs(wrapped.timeS - (a + 0.03)) < 1e-9, "wraps by the overshoot, not to zero");
  assert.equal(wrapped.playing, true, "a looped part repeats silently — playback never stops");
  assert.equal(advance(0, 0.1, o).timeS, a, "a playhead before the loop snaps into it");
  // A huge step (a stalled tab) still lands inside the loop rather than past it.
  const jumped = advance(a, 999, o);
  assert.ok(jumped.timeS >= a && jumped.timeS < b);
});

test("play all stops on the last count and stays there", () => {
  const o = { mode: "all" as const, grid: base.grid, loop: { startCount: 1, endCount: 8 }, endS };
  assert.deepEqual(advance(1, 0.1, o), { timeS: 1.1, playing: true });
  assert.deepEqual(advance(endS - 0.01, 0.1, o), { timeS: endS, playing: false });
});

test("a loop clipped by the end of the clip still loops", () => {
  // Part 4 runs to count 30, but count 31 would sit past the last sample slot.
  const loop = { startCount: 25, endCount: 30 };
  const o = { mode: "loop" as const, grid: base.grid, loop, endS };
  const [a] = loopTimesS(base.grid, loop);
  const r = advance(endS - 0.001, 0.5, o);
  assert.ok(r.timeS >= a && r.timeS <= endS, "wrapped inside the clip, not past its end");
  assert.equal(r.playing, true);
});
