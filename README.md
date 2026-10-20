# stepwise

Upload a short one-camera dance clip and get the dancer back as a 3D body you
can orbit, mirror, slow down and step through count by count, next to the
original video.

Deployed at <https://stepwise.sreshta-talluri.workers.dev> (no custom domain
yet). Adding a video file works for anyone. Pasting a TikTok or YouTube link
needs an invite code.

## Demo

> **TODO:** demo GIF or video goes here. No dancer has given permission yet for
> a public demo clip (`evaluation/clips.yaml`, entry `demo-public`), so there
> is nothing to show here yet.

## How it works

```
clip ─► RTMO detection + ByteTrack ─► track hygiene ─► SAM 3D Body, per frame (L40S)
                                                              │
       GLB per dancer (pymomentum) ◄─ Kalman smoothing ◄─ bone constraints
                                                              
audio ─► Beat This! beats ─► least-squares beat grid ─► kick rule picks count 1
```

1. **Detect and track.** RTMO (Apache-2.0, via rtmlib) finds people in frames
   sampled at 15 fps, and ByteTrack links them across frames. Track hygiene
   then merges split or duplicate tracks and drops blips and mirror
   reflections, before any GPU time is spent.
2. **Reconstruct.** Meta's SAM 3D Body runs on each frame on a Modal L40S and
   returns a 3D body for every tracked dancer.
3. **Clean up.** Each dancer's bone lengths are held constant for the whole
   clip, then every joint goes through a Kalman filter.
4. **Export.** One GLB per dancer, written by pymomentum on a CPU container,
   plus a `MotionResult` JSON (schema in `packages/motion-contract/`).
5. **Counts.** Beat This! finds the beats, a least-squares fit lays a steady
   grid through them, and a kick-drum rule picks count 1. This runs on CPU in
   parallel with the GPU work (`packages/beat-detect/`). The lesson shows a
   count as a proposal, and the dancer can tap it in by hand instead.

**Limits.** A single camera sees one side of a dancer. The pipeline tracks the
body through turns, so you can orbit round and see what the arms were doing
with the back to the camera. It does not invent what it never saw: parts
hidden by another dancer or outside the frame are marked uncertain or absent
and drawn that way (`docs/DESIGN.md` §7h).

## Architecture

| Piece | What runs it |
|---|---|
| Job API | FastAPI on Modal (`services/motion-api/api.py`). Answers only the frontend Worker, rate-limited per IP |
| GPU worker | Modal L40S, one container per job. Models load once per container |
| Export and beat tracking | Modal CPU containers |
| Job state | Postgres on Neon |
| Assets (video, GLB, MotionResult) | Cloudflare R2, served through presigned URLs |
| Frontend | Next.js + React Three Fiber (`apps/web/`), on a Cloudflare Worker via OpenNext |
| Errors | Sentry, backend and browser |
| Product analytics | First-party events in Postgres, with dashboards in PostHog |
| CI | GitHub Actions (`.github/workflows/test.yml`), nine checks on every push and PR |

`docs/DEPLOYMENT.md` records what is deployed, how to deploy it and the runbook.

## Measured performance

These numbers come from `docs/research/pipeline-latency.md` and the commit
messages cited. The samples are small, so read them as a few real runs and not
as benchmarks.

**Time to a finished lesson.** These are the §7 runs on one 14.4 s clip
(216 frames, one dancer), measured from when the request arrives:

| | Total |
|---|---|
| Before the overhead fixes | 225.6 s, plus ingest |
| After, cold GPU (4 runs) | 130–150 s |
| After, warm GPU (3 runs) | 109–129 s |

The "after" runs used a simulated 5 s ingest on a temporary app, not the
production one. Six earlier production jobs (12–48 s clips, before these
fixes) took 196–436 s. The 436 s job spent 286 s waiting for GPU capacity
just to export, and that wait is why export moved to CPU.

**Reconstruction speed.** 0.34–0.6 s per frame (1.7–3.4 fps), with peak VRAM
of 3.7 GB out of 48 GB. On 35–48 s clips, this step is 56–63 % of total time.
It runs one frame at a time in fp32. The vendored compile, bf16 and batching
speedups are not turned on yet, so this is the model's slowest configuration.

**Export, CPU against L40S.** The GLB bytes come out identical (same sha256)
on both. Export takes 11.0 s on 2 CPUs and 10.0 s on the L40S, and costs under
$0.001 per export on CPU against about $0.040 on the GPU (Modal list prices,
September 2026).

**Beats and counts.**
- Beat grid: 4 of 4 hand-labelled clips land within 70 ms (`d74a067`).
- Count 1: 7 of 10 owner-labelled clips are right. The three misses are all
  around 150 BPM and one beat off. Their count-1 confidence was 0.00–0.16,
  against 0.71–1.00 for correct picks, so the lesson says "Not sure where 1 is"
  for them (`8de0fb6`).

**Track hygiene.** Two solo clips that came out as four "dancers" (a double
detection box, swapped ids, a blip) now come out as one (`c53099a`).

**Not measured.** The repo has no ground-truth 3D accuracy number (such as
MPJPE) for the reconstruction. The evaluation set is 17 clips in
`evaluation/clips.yaml`: 10 core, 3 stress, 2 that must be refused, 1 group
and 1 demo. Each entry records the failure it is there to catch. The videos
are kept out of git.

## Layout

```
packages/motion-contract/   MotionResult schema, generated types, fixtures
packages/beat-detect/       beat tracking and count proposal
services/motion-api/        FastAPI job service + Modal GPU/CPU workers
apps/web/                   Next.js + React Three Fiber viewer
evaluation/                 eval clip manifest and hand labels
docs/                       PRD, design system, deployment, research
```

## Start here

| You want to | Read |
|---|---|
| Understand the plan and the feasibility gate | `docs/PRD.md` |
| See what is deployed and how | `docs/DEPLOYMENT.md` |
| Make any visual decision | `docs/DESIGN.md` (required before touching UI) |
| Know what is still undecided | `docs/OPEN-DECISIONS.md` |
| Contribute | `CONTRIBUTING.md` |
| Look up a term | `docs/CONCEPTS.md` |

An earlier prototype is kept at tag `archive/mock-pipeline-2026-03` and branch
`archive/v1`. It never had a working CV pipeline, because the viable models
depended on SMPL (non-commercial) and the planned detector was AGPL.

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
