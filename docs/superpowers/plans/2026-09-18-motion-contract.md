# packages/motion-contract Implementation Plan

> **For agentic workers:** This plan is executed inline in the same session that wrote it (full context already loaded from PRD/DESIGN/OPEN-DECISIONS). No handoff.

**Goal:** Freeze `MotionResult v1` — the JSON contract between the GPU pipeline and every downstream consumer (viewer, job API, share-clip generator) — plus generated TS/Python types, two hand-written fixtures, a validator, and tests.

**Architecture:** JSON Schema (draft 2020-12) is the single source of truth in `schema/`. TypeScript types and Python pydantic models are generated from it by committed codegen scripts (output committed too, so consumers don't need the generator installed). Fixtures are hand-authored JSON validated against the schema plus custom invariant checks the schema alone can't express (array-length parity, monotonic timestamps, joint-index consistency).

**Tech Stack:** JSON Schema 2020-12, TypeScript + `ajv` + `json-schema-to-typescript`, Python + `pydantic` v2 + `jsonschema` + `datamodel-code-generator` (uv-managed), `node:test`/`pytest` for tests.

**Spec:** `docs/PRD.md` §3 (pipeline, exact pins), §6 (the contract — field list); `docs/DESIGN.md` §4 (uncertainty language: observed/uncertain/absent), §7 (navigation — parts/counts, informs what the contract must expose for authoring); `docs/OPEN-DECISIONS.md` (E2, E3 noted but not blocking — see below); `docs/TASKS.md` W3.

## Global constraints (verbatim from spec)

- `schema_version` field required.
- `sample_times_s`: timestamp for **every** sample on the normalized video timeline, including suppressed/failed ones. Array index + nominal fps is explicitly insufficient. This is the single most important field.
- Every array/tensor field's shape and axis order must be stated in its schema `description` — not just implied.
- Joint hierarchy: rest pose, rotation convention, parent links must be explicit.
- Joint → GLB node name mapping, and an animation clip id.
- Per-joint **provenance** (observed / interpolated / suppressed:out_of_frame / suppressed:low_confidence — these are not mutually exclusive: a sample can be observed-then-interpolated-then-suppressed in combination) kept as a **separate field** from **visibility** (the DESIGN.md §4 three-state render taxonomy: `observed`/`uncertain`/`absent`). Never derive one from the other implicitly — both are stored.
- Video dimensions, orientation, audio offset.
- Camera intrinsics + camera-to-world transform.
- Root trajectory, per person.
- Crop rectangles for hands/feet close-ups.
- Immutable asset ids, kept separate from expiring signed URLs (no signed URLs in this schema at all).
- Per-clip accent colour (DESIGN.md §3 — sampled from the clip, persisted so viewer and share-card agree).
- `model_report`: model versions + license flags.
- Job status/error/retry is a **separate** schema (`job-status.schema.json`), never mixed into `MotionResult` (which only ever describes a *finished* job).
- Honesty boundary (DESIGN.md §7h): schema must be able to represent "tracked while turned away, lower confidence" (case 1 — best claim, must not be undersold) distinctly from "occluded/absent" (cases 2/3 — must never look recovered). This is why `visibility` has three states, not two, and why `suppressed:low_confidence` is distinct from `suppressed:out_of_frame`.

## Open-decisions check

- **E3 (mesh-region masking)** is flagged "affects the export format, decide before contract freezes." Resolution for *this* contract: the JSON contract carries per-joint `visibility` and conservative region-suppression semantics (documented: a suppressed wrist implies the hand region is `absent`/`uncertain` for rendering purposes) — it does **not** prescribe *how* the GLB encodes hidden surfaces (separate meshes vs. vertex masks vs. blend shapes). That technique choice lives entirely in the exporter/W10 and does not change any JSON field here. Not a blocker; documented as an explicit non-decision in the schema's top-level description.
- **E2 (uncertain-limb render)** is a viewer/shader concern (W5), not a data-contract concern. Not a blocker.
- No other OPEN item touches this package. Proceeding.

## File structure

```
packages/motion-contract/
  README.md                          overview, how to regenerate, how to validate
  schema/
    motion-result.schema.json        MotionResult v1 — the finished-job contract
    job-status.schema.json           separate job status/error/retry contract
  scripts/
    generate-ts.mjs                  schema -> src/ts/generated/*.ts (json-schema-to-typescript)
    generate-python.sh                schema -> python/motion_contract/generated/*.py (datamodel-code-generator via uv)
  src/ts/
    generated/
      motion-result.ts               generated, committed
      job-status.ts                  generated, committed
    validate.ts                      ajv compile + custom invariant checks
    index.ts                         public exports
  test/ts/
    validate.test.ts                 node:test — fixtures pass, mutated copies fail
  python/
    pyproject.toml
    motion_contract/
      __init__.py
      generated/
        motion_result.py             generated, committed
        job_status.py                generated, committed
      validate.py                    jsonschema validate() + custom invariant checks
    tests/
      test_validate.py               pytest — fixtures pass, mutated copies fail
  fixtures/
    README.md                        what each fixture exercises
    good-lesson.json                 ~14s, 1 dancer, 30 counts, 15fps, clean
    failure-lesson.json              suppressed frames, feet cropped, grounding_status "none", dropout + re-entry
  package.json                       node scripts: generate, validate, test
```

## Task 1 — `schema/motion-result.schema.json`

The core deliverable. JSON Schema draft 2020-12. Every array field's `description` states shape/axis order/units explicitly. Encodes all Global Constraints above. `$id`: `https://stepwise.dev/schema/motion-result/v1.json` (namespaced but never fetched — repo is source of truth).

- [ ] Write the schema (top-level object, `$defs` for `Provenance`, `Visibility`, `Quaternion`, `Vec3`, `JointDef`, `PersonResult`, `Sample`, `CropRect`, `ModelReportEntry`).
- [ ] Self-check: every field named in Global Constraints appears. Grep the schema file for each constraint keyword.
- [ ] Commit.

## Task 2 — `schema/job-status.schema.json`

Small, separate. `job_id`, `state` enum (`queued`/`processing`/`succeeded`/`failed`), `stage_message` (plain-language, per DESIGN §7c — "Building the body — count 9 of 32", never a bare percentage), `progress` (0-1, optional, UI treats as rough only), `error` (`code`, `message`, `retryable`) nullable, `retry_count`.

- [ ] Write the schema.
- [ ] Commit.

## Task 3 — Node package + codegen

- [ ] `package.json` with `ajv`, `ajv-formats`, `json-schema-to-typescript`, `tsx`, `typescript` as deps; scripts `generate`, `validate`, `test`.
- [ ] `scripts/generate-ts.mjs` reading both schemas, emitting `src/ts/generated/motion-result.ts` and `job-status.ts`.
- [ ] Run it, commit generated output alongside the script (generated files ARE committed — consumers shouldn't need the toolchain).

## Task 4 — Python package + codegen

- [ ] `python/pyproject.toml` (pydantic v2, jsonschema; uv-managed).
- [ ] `scripts/generate-python.sh` invoking `datamodel-code-generator` via `uv run`.
- [ ] Run it, commit generated output.

## Task 5 — Fixtures

- [ ] `fixtures/good-lesson.json`: 14.0s @ 15fps = 210 samples, 1 person, 30 counts worth of plausible joint motion (simple periodic arm/leg swing, not literally hand-animated frame-by-frame — a small generator script producing smooth, physically-plausible-looking rotations is acceptable and faster than hand-typing 210 frames; script is throwaway, output is the committed artifact). All `observed`, `grounding_status: "grounded"`, real floor plane, accent colour sampled, camera static.
- [ ] `fixtures/failure-lesson.json`: shorter clip is fine (~6s). Encodes: a suppressed span mid-clip (`suppressed:low_confidence` — occlusion), a suppressed span from `suppressed:out_of_frame` for feet specifically (feet cropped for most of the clip → `grounding_status: "none"`, `floor_plane: null`), a dropout followed by re-entry (provenance returns to `observed` after the gap, demonstrating the contract supports resuming — this is what a viewer would seek across). `crop_rects.feet` mostly `null` (cropped out) to match the honesty boundary (never claim recovered feet).
- [ ] `fixtures/README.md` documenting exactly what each fixture exercises and why (mid-playback dropout, seeking across a gap via `sample_times_s`, re-entry).
- [ ] Both validate against the schema (Task 6 must exist first, or validate manually via ajv CLI — order tasks so validator lands before fixtures are declared done).

## Task 6 — Validator (TS)

Schema-only validation misses cross-field invariants. Write `src/ts/validate.ts`:
- `sample_times_s.length === persons[i].samples.length` for every person.
- `sample_times_s` strictly increasing.
- every `samples[i].joints` array has the same length as `joint_hierarchy.joints` and indices line up.
- if `grounding_status === "none"` then `floor_plane === null`.
- if a joint's `visibility === "absent"` its `provenance.suppressed` must be non-null (can't be absent without a suppression reason).

- [ ] Write failing test in `test/ts/validate.test.ts` for one invariant (e.g. mismatched array length) using `node:test`.
- [ ] Run, confirm fails (function doesn't exist yet).
- [ ] Implement `validate.ts` (ajv schema check + the invariants above), returning `{valid: boolean, errors: string[]}`.
- [ ] Run, confirm passes; add remaining invariant tests + both fixtures pass; add mutated-copy tests for each invariant.
- [ ] Commit.

## Task 7 — Validator (Python)

Mirror of Task 6 in `python/motion_contract/validate.py` using `jsonschema` for schema check + the same hand-written invariants. `pytest` tests in `python/tests/test_validate.py` mirroring the TS test cases (fixtures pass, mutated copies fail).

- [ ] Write failing tests.
- [ ] Implement `validate.py`.
- [ ] Run, confirm passes.
- [ ] Commit.

## Task 8 — README + wiring

- [ ] `packages/motion-contract/README.md`: what this package is, why it's frozen, how to regenerate types, how to validate a `MotionResult` blob, pointer to fixtures.
- [ ] Root `README.md` already references this package — verify the "Layout" table still matches reality; update only if wrong.
- [ ] Commit.

## Task 9 — Final check + push

- [ ] `npm run validate` (or equivalent) against both fixtures — must pass.
- [ ] `npm test` and `pytest` — all green.
- [ ] Push branch `motion-contract`. Do not merge to main/rebuild-v4.

---

## Self-review notes

- Spec coverage: every Global Constraints bullet has a corresponding schema field (Task 1) — verified by the grep self-check in Task 1.
- No placeholders: fixture content is fully specified (real numbers, not TBD) at generation time in Task 5.
- Type consistency: `Provenance` and `Visibility` are defined once in `$defs` and reused everywhere (joints, root trajectory) — both TS and Python codegen inherit this from the single schema, so no drift is possible between the two languages.
