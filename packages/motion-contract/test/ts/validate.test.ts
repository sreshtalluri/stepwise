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

test("a document with no beat_proposal at all is valid — absence means nobody asked", () => {
  const doc = loadFixture("failure-lesson.json");
  assert.equal("beat_proposal" in doc, false, "failure-lesson must stay the no-proposal fixture");
  assert.equal(validateMotionResult(doc).valid, true);
});

test("good-lesson carries a confident beat proposal, two-dancer carries a doubted one", () => {
  const confident = loadFixture("good-lesson.json").beat_proposal;
  assert.equal(confident.warnings.length, 0);
  assert.ok(confident.confidence > 0.9);

  // The honesty case: a proposal that made it into the document while knowing
  // it is probably a half/double-time lock. The warning and the alternates are
  // what a consumer must carry through; a bare grid would strip them.
  const doubted = loadFixture("two-dancer-lesson.json").beat_proposal;
  assert.ok(doubted.confidence <= 0.4);
  assert.ok(doubted.warnings.some((w: string) => w.includes("half/double-time")));
  assert.deepEqual(
    doubted.alternates.map((a: { label: string }) => a.label).sort(),
    ["double-time", "half-time"],
  );
});

test("rejects a beat_proposal confidence outside 0..1", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.beat_proposal.confidence = 1.4;
  assert.equal(validateMotionResult(doc).valid, false);
});

test("rejects a beat_proposal whose count_total describes a different timeline", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  // The classic mistake this guards: counting against source_video.duration_s
  // of some other clip, or forgetting to recompute after changing the spacing.
  doc.beat_proposal.count_total = 120;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("describes a different timeline")));
});

test("rejects an alternate that is not a half/double re-reading of the same grid", () => {
  const doc = clone(loadFixture("good-lesson.json"));
  doc.beat_proposal.alternates[0].seconds_per_count = 0.31;
  const result = validateMotionResult(doc);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("must re-read the same grid")));
});

test("rejects a beat_proposal missing the fields that make it a proposal rather than a fact", () => {
  // confidence / alternates / warnings are required precisely so a producer
  // cannot ship a bare grid that reads as ground truth (DESIGN.md §7h).
  for (const field of ["confidence", "alternates", "warnings", "bpm"]) {
    const doc = clone(loadFixture("good-lesson.json"));
    delete doc.beat_proposal[field];
    assert.equal(validateMotionResult(doc).valid, false, `deleting beat_proposal.${field} must fail validation`);
  }
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
