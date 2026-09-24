# motion-contract

`MotionResult v1` — the frozen, versioned JSON contract between the GPU motion
pipeline (`services/motion-api`) and every consumer of a finished job (the
viewer in `apps/web`, the share-clip generator). See `docs/PRD.md` §6 and
`docs/TASKS.md` W3 for why this package exists and why it's built before the
pipeline or the viewer: both halves build and test against the fixtures here
independently.

Job status/error/retry (`JobStatus`) is a **separate** contract
(`schema/job-status.schema.json`) — `MotionResult` only ever describes a
*finished* job.

## Layout

```
schema/                 JSON Schema (draft 2020-12) — the single source of truth
src/ts/generated/       TypeScript types, generated from schema/, committed
src/ts/validate.ts      ajv schema check + cross-field invariants schema alone can't express
python/motion_contract/generated/   pydantic v2 models, generated from schema/, committed
python/motion_contract/validate.py  jsonschema check + the same invariants, mirrored
fixtures/               two hand-authored example MotionResult documents (see fixtures/README.md)
scripts/                codegen + fixture-generation + a validate CLI
```

## Versioning rule

Recorded 2026-09-20, when adding `beat_proposal` made it necessary. It had
been implied by the word "frozen" and by one line in the schema ("bump on any
breaking field change"), which turned out not to be specific enough to settle
an actual case.

**Bump `schema_version` when a consumer written against the previous version
could misread a conforming document.** Concretely: a property removed, moved
to a different parent, retyped, newly required, or given different semantics
under the same name.

**Do not bump for a purely additive optional property.** Every document that
was valid before is still valid, and every consumer that ignores unknown keys
is unaffected. `beat_proposal` is exactly this case, so the contract stays at
`1.0.0`.

There is a wrinkle, and it is the reason the rule needs a second half. These
schemas are `additionalProperties: false`, so a **pinned old copy of the
schema will reject a new document** even though nothing breaking happened. The
paired consumer rule: validate against the schema shipped alongside the code
you are running, and treat `schema_version` — not the property set — as the
compatibility signal. Do not vendor a copy of the schema and keep validating
against it.

**One precedent, recorded rather than quietly fixed.** Commit `8791e3f` moved
`animation` from a required top-level field onto each `persons[]` entry and
left the version at `1.0.0`. By the rule above that was a bump-class change —
and `docs/INTEGRATION.md` §3.1 is the record of it breaking a real consumer
that had not been told. It is deliberately **not** retro-bumped: no consumer
had shipped against the old shape, and renumbering now would invalidate every
committed fixture and every stored result for no reader benefit. The rule
binds from `beat_proposal` forward.

## Regenerating types

The generated files under `src/ts/generated/` and
`python/motion_contract/generated/` are committed so downstream packages don't
need the codegen toolchain installed — but they must never be hand-edited.
After changing a `schema/*.schema.json` file:

```
npm run generate                      # -> src/ts/generated/*.ts
bash scripts/generate-python.sh       # -> python/motion_contract/generated/*.py
```

## Validating a document

```
npm run validate      # validates every fixtures/*.json (TS/ajv)
npm test              # + invariant unit tests (node:test)
uv run --project python pytest     # Python equivalent
```

Both validators do two things: a JSON Schema check, then a handful of
cross-field invariants the schema can't express on its own (array-length
parity against `sample_times_s`, monotonic timestamps, joint-index
consistency, and the rule that an `absent` joint must carry a suppression
reason). See `src/ts/validate.ts` / `python/motion_contract/validate.py`.

## Why the fields are shaped this way

The full rationale for every field lives in the `description` strings inside
`schema/motion-result.schema.json` itself — read the schema, not a summary of
it, since that's what stays in sync. A few load-bearing decisions worth
flagging up front:

- **`sample_times_s`** is the single most important field. It timestamps every
  sample slot, including fully suppressed ones — array index plus a nominal
  fps is not sufficient once frame drops exist, and this is what playback,
  seeking, and re-entry after a gap are computed against.
- **`provenance` and `visibility` are separate fields**, not derived from one
  another. A sample can be `observed` *and* `interpolated` *and* `suppressed`
  at once (see `fixtures/failure-lesson.json`) — that's a real pipeline state,
  not an edge case to normalize away.
- **Immutable asset ids, never signed URLs.** `source_video.asset_id` and
  `animation.glb_asset_id` are stable ids; resolving an id to a fetchable,
  expiring URL is a separate lookup at render time and deliberately outside
  this contract.
- **`beat_proposal` is a proposal, and the schema makes that structural.**
  `confidence`, `bpm`, `alternates` and `warnings` are all *required* when the
  object is present, so a producer cannot emit a bare `{countOneS,
  secondsPerCount, countTotal}` that reads as ground truth. The counts the
  *learner* authors are deliberately NOT in this document: `MotionResult`
  describes a finished job and never changes after it is written, while
  authored structure is mutable and per-learner. It lives client-side for now
  (`apps/web/lib/lessonStructure.ts`) because `OPEN-DECISIONS.md` D5
  (accounts) is unresolved and there is no identity to key it by.
- **Mesh-region masking technique is out of scope here** (`OPEN-DECISIONS.md`
  E3). This contract guarantees per-joint `visibility`/`provenance` exist for
  any exporter technique to consume; it does not choose between separate
  meshes, vertex masks, or blend shapes.
