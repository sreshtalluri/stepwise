# stepwise

Learn a dance from any clip, in 3D.

Upload a short video filmed on one front-facing camera. Get the dancer back as a
stylized 3D body you can orbit, mirror, slow down, and step through part by part
and count by count — alongside the original video.

**Status: rebuild in progress.** This branch is a fresh start. The previous
implementation is preserved at tag `archive/mock-pipeline-2026-03` and branch
`archive/v1`; it used mock adapters and never had a working CV pipeline, because
every viable model depended on SMPL (non-commercial) and the planned detector was
AGPL. Both problems are now solved — see `docs/PRD.md`.

## What it does, honestly

A single camera sees one side of a dancer. From that, the pipeline recovers a 3D
body and tracks it — including through turns, so you can orbit round and see what
their arms were doing when their back was to the camera. That is the point of the
product.

What it does **not** do is invent what it never saw. Parts blocked by another
dancer, or outside the frame, are marked as uncertain or absent and rendered as
such. See `docs/DESIGN.md` §7h for the exact boundary.

## Layout

```
packages/motion-contract/   MotionResult schema, generated types, fixtures
services/motion-api/        FastAPI job service + GPU worker
apps/web/                   Next.js + React Three Fiber viewer
docs/                       PRD, design system, open decisions, task breakdown
```

The contract is frozen early on purpose: the web app builds against a recorded
fixture, so the frontend and the pipeline can be developed in parallel.

## Start here

| You want to | Read |
|---|---|
| Understand the plan and the feasibility gate | `docs/PRD.md` |
| Make any visual decision | `docs/DESIGN.md` (required before touching UI) |
| Know what is still undecided | `docs/OPEN-DECISIONS.md` |
| Pick up a work package | `docs/TASKS.md` |
| Look up a term | `docs/CONCEPTS.md` |

## Licensing

This repository is **mixed-licence, and cannot be honestly labeled MIT or
Apache-2.0 as a whole.** Code written here is MIT (`LICENSE`). It also depends
on Meta's SAM 3D Body, distributed under the **SAM License** — a custom,
non-OSI-approved licence, verbatim copy at `SAM Materials/LICENSE` — and the
SAM-derived parts of this project stay under that licence forever, regardless
of what licence the surrounding code carries. See `NOTICE` for the short
version.

The SAM License carries obligations that pass through to anyone who receives
this work:

- It **prohibits** use for ITAR-controlled purposes or military/warfare,
  nuclear, espionage, or illegal-weapons end uses.
- It requires acknowledging the SAM Materials **if you publish research
  results** produced using them — this applies to research papers, not to
  running stepwise as a hosted product.
- Meta may amend the licence unilaterally at any time; continued use counts
  as accepting the amendment.

Making this repository public is our choice, not something the licence
requires.

`docs/LICENSES.md` maps every dependency and its obligations in full,
including the MHR body-model assets, whose licence has not yet been verified
(it ships inside a separate `assets.zip` download). The detector is RTMO
(Apache-2.0) via rtmlib, deliberately chosen over Ultralytics YOLO because
AGPL-3.0 and the SAM License cannot be combined in one program.
