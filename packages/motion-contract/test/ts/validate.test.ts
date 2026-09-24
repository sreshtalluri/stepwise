import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { validateMotionResult, validateJobStatus } from "../../src/ts/validate.js";

const root = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const loadFixture = (name: string) => JSON.parse(readFileSync(path.join(root, "fixtures", name), "utf-8"));

// Deep clone via JSON round-trip so mutations in one test never leak into another.
const clone = (doc: unknown) => JSON.parse(JSON.stringify(doc));

test("good-lesson.json fixture is a valid MotionResult", () => {
  const result = validateMotionResult(loadFixture("good-lesson.json"));
  assert.deepEqual(result.errors, []);
  assert.equal(result.valid, true);
});

test("failure-lesson.json fixture is a valid MotionResult", () => {
  const result = validateMotionResult(loadFixture("failure-lesson.json"));
  assert.deepEqual(result.errors, []);
  assert.equal(result.valid, true);
});

test("failure-lesson.json actually exercises observed+interpolated+suppressed simultaneously", () => {
  const doc = loadFixture("failure-lesson.json");
  const triple = doc.persons[0].samples
    .flatMap((s: any) => s.joints)
    .some((j: any) => j.provenance.observed === true && j.provenance.interpolated === true && j.provenance.suppressed !== null);
  assert.equal(triple, true, "fixture must contain at least one joint sample with all three provenance flags active at once");
});

test("per-side crop tracks are optional, and length-checked when present", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  const n = doc.sample_times_s.length;
  doc.persons[0].crop_rects.left_hand = Array(n).fill(null);
  assert.deepEqual(validateMotionResult(doc).errors, []);
  doc.persons[0].crop_rects.left_hand.pop();
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("crop_rects.left_hand length")));
});

test("rejects a document missing schema_version", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  delete doc.schema_version;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
});

test("rejects non-monotonic sample_times_s", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.sample_times_s[5] = doc.sample_times_s[4];
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("strictly increasing")));
});

test("rejects sample_times_s / samples length mismatch", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.persons[0].samples.pop();
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("samples length")));
});

test("rejects sample_times_s / root_trajectory length mismatch", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.persons[0].root_trajectory.pop();
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("root_trajectory length")));
});

test("rejects a sample whose joints array length doesn't match joint_hierarchy", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.persons[0].samples[0].joints.pop();
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("joints length")));
});

test("rejects a joint marked absent with no suppression reason", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.persons[0].samples[0].joints[0].visibility = "absent";
  doc.persons[0].samples[0].joints[0].provenance.suppressed = null;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes('visibility "absent"')));
});

test("rejects grounding_status none paired with a non-null floor_plane", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.grounding.status = "none";
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes('grounding.status is "none"')));
});

test("rejects grounding_status grounded paired with a null floor_plane", () => {
  const doc = clone(loadFixture("failure-lesson.json"));
  doc.grounding.status = "grounded";
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes('floor_plane is null')));
});

test("rejects a joint_hierarchy whose index doesn't match its array position", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.joint_hierarchy.joints[3].index = 99;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("must equal 3")));
});

test("proposed_counts is optional — a document without one is still valid", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  delete doc.proposed_counts;
  const result = validateMotionResult(doc);
  assert.deepEqual(result.errors, []);
  assert.equal(result.valid, true);
});

test("rejects a proposed grid sized against something other than sample_times_s", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  // The realistic way to get this wrong: size the grid against
  // source_video.duration_s (14.0) instead of sample_times_s[N-1] (13.933...).
  // It is off by exactly one count and nothing else in the document notices.
  doc.proposed_counts.count_total += 1;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("authoritative timeline")));
});

test("a weak proposal still travels with its alternates and its reason", () => {
  const doc = loadFixture("failure-lesson.json");
  // The honesty rule has teeth only if the doubt survives the trip: a consumer
  // that gets the grid must also get the confidence, the half-time reading and
  // the plain-language reason, or it cannot be quieter about a weak guess.
  assert.ok(doc.proposed_counts.confidence < 0.5);
  assert.ok(doc.proposed_counts.warnings.length > 0);
  assert.deepEqual(
    doc.proposed_counts.alternates.map((a: any) => a.label).sort(),
    ["double-time", "half-time"],
  );
});

test("job-status: a minimal queued job is valid", () => {
  const result = validateJobStatus({
    schema_version: "1.0.0",
    job_id: "job_abc",
    state: "queued",
    stage_message: "",
    progress: null,
    error: null,
    retry_count: 0,
  });
  assert.deepEqual(result.errors, []);
  assert.equal(result.valid, true);
});

test("job-status: rejects an unknown state", () => {
  const result = validateJobStatus({
    schema_version: "1.0.0",
    job_id: "job_abc",
    state: "bogus",
    stage_message: "",
    progress: null,
    error: null,
    retry_count: 0,
  });
  assert.equal(result.valid, false);
});
