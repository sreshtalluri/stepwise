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
