import { test } from "node:test";
import assert from "node:assert/strict";

import {
  builtNote,
  detectionIndex,
  eightAt,
  eightSpan,
  eightTimes,
  eightTotal,
  flowSteps,
  gridFromCounts,
  handoffHref,
  parseHandoff,
  stripIndex,
  stripPosition,
  type Detections,
} from "../lib/flow";
import type { JobStatus } from "../lib/jobStatus";

const COUNTS = { bpm: 120, count_one_s: 0.5, seconds_per_count: 0.5, confidence: 0.9 };

test("the grid matches the lesson's own derivation (motion_result._proposed_counts)", () => {
  // (20 - 0.5) // 0.5 + 1 = 40 counts, five eights.
  const g = gridFromCounts(COUNTS, 20);
  assert.deepEqual(g, { countOneS: 0.5, secondsPerCount: 0.5, countTotal: 40 });
  assert.equal(eightTotal(g), 5);
  // A negative count 1 is clamped to the start, like the lesson.
  assert.equal(gridFromCounts({ ...COUNTS, count_one_s: -0.3 }, 20).countOneS, 0);
});

test("eights: under the playhead, their counts and their seconds", () => {
  const g = gridFromCounts(COUNTS, 21.2); // 42 counts: the last eight is short
  assert.equal(eightAt(g, 0), 1); // lead-in belongs to the first eight
  assert.equal(eightAt(g, 0.5 + 8 * 0.5), 2);
  assert.equal(eightAt(g, 999), 6);
  assert.deepEqual(eightSpan(g, 6), { startCount: 41, endCount: 42 });
  assert.deepEqual(eightTimes(g, 1, 21.2), [0.5, 4.5]);
  assert.deepEqual(eightTimes(g, 6, 21.2), [20.5, 21.2]); // kept inside the clip
});

test("the strip is dark in the lead-in and wraps every eight", () => {
  const g = gridFromCounts(COUNTS, 20);
  assert.equal(stripIndex(g, 0.2), -1);
  assert.equal(stripIndex(g, 0.5), 0);
  assert.equal(stripIndex(g, 0.5 + 7 * 0.5), 7);
  assert.equal(stripIndex(g, 0.5 + 8 * 0.5), 0);
  // The dot stays over the active count's tick for the whole count.
  const t = 0.5 + 3.9 * 0.5; // late in count 4
  assert.equal(stripIndex(g, t), 3);
  assert.ok(stripPosition(g, t) >= 3 / 8 && stripPosition(g, t) < 4 / 8);
});

function status(over: Partial<JobStatus>): JobStatus {
  return {
    schema_version: "1.0.0",
    job_id: "job_x",
    state: "processing",
    stage_message: "",
    progress: 0.3,
    error: null,
    retry_count: 0,
    ...over,
  };
}

test("every done step is backed by a milestone, not by the progress fraction", () => {
  const [, dancers, counts, body] = flowSteps(status({ progress: 0.9 }), null);
  assert.equal(dancers.state, "now");
  assert.equal(counts.state, "now");
  assert.equal(body.state, "wait");

  const g = gridFromCounts(COUNTS, 20);
  const s = flowSteps(
    status({ milestones: { counts: COUNTS, dancers: 2, frames_done: 150, frames_total: 300 } }),
    g,
  );
  assert.deepEqual(s.map((x) => x.state), ["done", "done", "done", "now"]);
  assert.equal(s[1].note, "2 dancers");
  assert.equal(s[2].note, "120 a minute, 5 eight-counts");
  assert.equal(s[3].note, "2 of 5 eight-counts built");

  // Counts can land while still queued: they do not wait for a GPU.
  const q = flowSteps(status({ state: "queued", progress: null, milestones: { counts: COUNTS } }), g);
  assert.equal(q[2].state, "done");
  assert.equal(q[1].state, "wait");

  const done = flowSteps(status({ state: "succeeded", progress: 1 }), null);
  assert.ok(done.every((x) => x.state === "done"));
});

test("frames stand in for eights until the counts are known", () => {
  assert.equal(builtNote(40, 300, null), "Frame 40 of 300");
});

test("the handoff round-trips speed and loop, and drops anything it does not know", () => {
  const href = handoffHref("job_a b", 0.5, { startCount: 9, endCount: 16 });
  assert.equal(href, "/lesson/job_a%20b?speed=0.5&loop=9-16");
  assert.equal(handoffHref("j", 1, null), "/lesson/j");

  const speeds = [0.25, 0.5, 0.75, 1];
  assert.deepEqual(parseHandoff("?speed=0.5&loop=9-16", speeds, 40), {
    speed: 0.5,
    loop: { startCount: 9, endCount: 16 },
  });
  assert.deepEqual(parseHandoff("?loop=41-48", speeds, 42), { speed: null, loop: { startCount: 41, endCount: 42 } });
  assert.deepEqual(parseHandoff("?speed=3&loop=9-2", speeds, 40), { speed: null, loop: null });
  assert.deepEqual(parseHandoff("?loop=50-56", speeds, 42), { speed: null, loop: null });
});

test("detections are looked up by time and end where the sampling ended", () => {
  const d: Detections = { fps: 5, width: 10, height: 10, times: [0, 0.2, 0.4], dancers: [] };
  assert.equal(detectionIndex(d, 0), 0);
  assert.equal(detectionIndex(d, 0.29), 1);
  assert.equal(detectionIndex(d, 0.45), 2);
  assert.equal(detectionIndex(d, 5), -1);
});
