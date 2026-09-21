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

  if (doc.grounding.status === "none" && doc.grounding.floor_plane !== null) {
    errors.push('grounding.status is "none" but floor_plane is not null — DESIGN.md §10 forbids a floor when grounding failed');
  }
  if (doc.grounding.status === "grounded" && doc.grounding.floor_plane === null) {
    errors.push('grounding.status is "grounded" but floor_plane is null');
  }

  // A proposed grid that disagrees with the timeline it is laid over is worse
  // than no proposal: the count strip would run out of counts, or show counts
  // past the end of the dance, with nothing anywhere saying why. Same formula as
  // `normalizeStructure` in packages/navigation/src/core.ts, against
  // sample_times_s rather than source_video.duration_s.
  const pc = doc.proposed_counts;
  if (pc) {
    const endS = doc.sample_times_s[n - 1];
    const expected = Math.max(1, Math.floor((endS - pc.count_one_s) / pc.seconds_per_count) + 1);
    if (pc.count_total !== expected) {
      errors.push(
        `proposed_counts.count_total is ${pc.count_total} but the grid over sample_times_s gives ${expected} — a proposal must be sized against the authoritative timeline`,
      );
    }
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
