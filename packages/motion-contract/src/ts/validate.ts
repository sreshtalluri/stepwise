import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import type { MotionResult } from "./generated/motion-result.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const schemaDir = path.join(here, "..", "..", "schema");

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

const motionResultSchema = JSON.parse(readFileSync(path.join(schemaDir, "motion-result.schema.json"), "utf-8"));
const jobStatusSchema = JSON.parse(readFileSync(path.join(schemaDir, "job-status.schema.json"), "utf-8"));

const validateMotionResultSchema = ajv.compile(motionResultSchema);
const validateJobStatusSchema = ajv.compile(jobStatusSchema);

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Invariants JSON Schema can't express: cross-field array-length parity,
 * monotonic sample_times_s, joint index consistency, and the
 * absent-implies-a-suppression-reason honesty rule.
 */
function checkInvariants(doc: MotionResult): string[] {
  const errors: string[] = [];
  const n = doc.sample_times_s.length;

  for (let i = 1; i < n; i++) {
    if (!(doc.sample_times_s[i] > doc.sample_times_s[i - 1])) {
      errors.push(
        `sample_times_s must be strictly increasing: index ${i} (${doc.sample_times_s[i]}) <= index ${i - 1} (${doc.sample_times_s[i - 1]})`,
      );
    }
  }

  const jointCount = doc.joint_hierarchy.joints.length;
  doc.joint_hierarchy.joints.forEach((j, i) => {
    if (j.index !== i) {
      errors.push(`joint_hierarchy.joints[${i}].index must equal ${i}, got ${j.index}`);
    }
  });

  doc.persons.forEach((person, pi) => {
    if (person.root_trajectory.length !== n) {
      errors.push(`persons[${pi}].root_trajectory length ${person.root_trajectory.length} !== sample_times_s length ${n}`);
    }
    if (person.samples.length !== n) {
      errors.push(`persons[${pi}].samples length ${person.samples.length} !== sample_times_s length ${n}`);
    }
    if (person.crop_rects.hands.length !== n) {
      errors.push(`persons[${pi}].crop_rects.hands length ${person.crop_rects.hands.length} !== sample_times_s length ${n}`);
    }
    if (person.crop_rects.feet.length !== n) {
      errors.push(`persons[${pi}].crop_rects.feet length ${person.crop_rects.feet.length} !== sample_times_s length ${n}`);
    }
    person.samples.forEach((sample, si) => {
      if (sample.joints.length !== jointCount) {
        errors.push(`persons[${pi}].samples[${si}].joints length ${sample.joints.length} !== joint_hierarchy.joints length ${jointCount}`);
      }
      sample.joints.forEach((joint, ji) => {
        if (joint.visibility === "absent" && joint.provenance.suppressed === null) {
          errors.push(
            `persons[${pi}].samples[${si}].joints[${ji}] has visibility "absent" but provenance.suppressed is null — an absent joint must carry a suppression reason`,
          );
        }
      });
    });
  });

  // beat_proposal is optional; when present it must be internally consistent
  // with the timeline it claims to describe. Neither rule is expressible in
  // JSON Schema, and both guard against a proposal that LOOKS fine field by
  // field while quietly describing a different clip or a different grid.
  const beat = doc.beat_proposal;
  if (beat) {
    // Same formula, and the same end-of-clip, as normalizeStructure() in
    // packages/navigation/src/core.ts: the clip ends at the last sample slot,
    // never at source_video.duration_s. Tolerance of one count, because a
    // boundary landing on the last sample is a float coin-flip, not an error.
    const endS = doc.sample_times_s[n - 1];
    const expected = Math.max(1, Math.floor((endS - beat.count_one_s) / beat.seconds_per_count) + 1);
    if (Math.abs(beat.count_total - expected) > 1) {
      errors.push(
        `beat_proposal.count_total is ${beat.count_total} but the grid (count_one_s ${beat.count_one_s}, seconds_per_count ${beat.seconds_per_count}) over a clip ending at ${endS}s yields ${expected} — the proposal describes a different timeline`,
      );
    }
    // An alternate is the SAME anchor re-read at half or double the
    // subdivision. If the spacing isn't exactly that, the "one tap to fix a
    // half/double lock" affordance the alternates exist for silently lies.
    for (const alt of beat.alternates) {
      const want = alt.label === "double-time" ? beat.seconds_per_count / 2 : beat.seconds_per_count * 2;
      if (Math.abs(alt.seconds_per_count - want) > 1e-4) {
        errors.push(
          `beat_proposal.alternates "${alt.label}" has seconds_per_count ${alt.seconds_per_count}, expected ${want} — an alternate must re-read the same grid, not propose an unrelated tempo`,
        );
      }
    }
  }

  if (doc.grounding.status === "none" && doc.grounding.floor_plane !== null) {
    errors.push('grounding.status is "none" but floor_plane is not null — DESIGN.md §10 forbids a floor when grounding failed');
  }
  if (doc.grounding.status === "grounded" && doc.grounding.floor_plane === null) {
    errors.push('grounding.status is "grounded" but floor_plane is null');
  }

  return errors;
}

export function validateMotionResult(doc: unknown): ValidationResult {
  const schemaOk = validateMotionResultSchema(doc);
  if (!schemaOk) {
    const errors = (validateMotionResultSchema.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message}`);
    return { valid: false, errors };
  }
  const invariantErrors = checkInvariants(doc as MotionResult);
  return { valid: invariantErrors.length === 0, errors: invariantErrors };
}

export function validateJobStatus(doc: unknown): ValidationResult {
  const ok = validateJobStatusSchema(doc);
  const errors = (validateJobStatusSchema.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message}`);
  return { valid: ok, errors };
}
