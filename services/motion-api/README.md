# motion-api

GPU pipeline: video in, `MotionResult` out. See `docs/PRD.md` for the plan.

## Modal setup

Two account prerequisites, both one-time:

1. **HuggingFace token.** Create a **read** token at
   <https://huggingface.co/settings/tokens>, then:
   ```sh
   modal secret create huggingface HF_TOKEN=hf_xxxxx --force
   ```
   It must belong to the same account that was granted access to
   `facebook/sam-3d-body-dinov3`.

2. **Payment method on Modal.** Required for *any* GPU function, even with free
   credit. <https://modal.com/settings/billing>

## Stages

Run in order. Each is independently runnable so a failure is diagnosable.

```sh
# stage 2 — gated access + cache the weights. CPU only, costs cents.
# Works before billing is set up thanks to the STEPWISE_GPU override.
STEPWISE_GPU= modal run modal_app.py::download_weights

# stage 3 — what actually landed in the Volume
STEPWISE_GPU= modal run modal_app.py::inspect_weights

# stage 1 — CUDA works on the card we plan to rent. Needs billing.
modal run modal_app.py::verify_gpu
```

## Two gotchas worth knowing

**Modal validates the whole app at load time.** A missing Secret or an
unaffordable GPU tier blocks *every* function in the file, including ones that
never touch it. Hence the `HF_SECRET` try/except and the `STEPWISE_GPU`
override — without them you cannot run a CPU function until billing is live.

**The environment pins are not arbitrary.** Python 3.11 / Torch 2.5.1 / cu124
comes from Fast-SAM-3D-Body's setup script, because Detectron2 compiles against
that CUDA toolkit. `pymomentum` is deliberately absent: its wheels target
Python 3.12/3.13 with Torch 2.8, which cannot coexist here. glTF export gets a
separate image and the two exchange plain arrays.

## W4: the HTTP layer (`api.py`)

`modal_app.py` is the GPU worker; `api.py` is the plain FastAPI service that
turns an HTTP upload into a dispatched Modal job and serves its status/result.
It never imports torch/CUDA/pymomentum.

**It is deployed, on Modal, as `modal_app.py::web`:**
<https://sreshta-talluri--stepwise-motion-web.modal.run>. `docs/DEPLOYMENT.md`
is the runbook -- what is live, what is blocked on which credential, and what to
do when it breaks. `modal deploy modal_app.py` ships the API and the GPU
functions together, because they are one app.

Running it on a laptop is unchanged and still the escape hatch -- the Modal
coupling is exactly one decorator deep:

```sh
brew install ffmpeg                # or: apt install ffmpeg. See "Dedupe" below.
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-api.txt
modal deploy modal_app.py          # api.py looks up run_clip via Function.from_name
.venv/bin/python -m uvicorn api:app --port 8811
```

### Where the bytes are (`storage.py`)

Video, GLBs and the materialised `MotionResult` live in **Cloudflare R2**;
`.npz` and the model weights stay on Modal Volumes. `GET /assets/{asset_id}`
answers **302** to an R2 URL that honours `Range:`, which is the whole reason
for the move: the old byte proxy read entire objects into memory and returned a
200, so video scrubbing could not work. `asset_id` is still opaque and
immutable, never a signed URL.

```sh
python3 verify_r2.py                         # laptop: write, range-read, delete
modal run modal_app.py::verify_r2_access     # the same, using the Modal Secret
python3 e2e_check.py <url> <clip.mp4>        # upload -> poll -> result -> 206
```

`e2e_check.py` costs one real GPU reconstruction. It is a deliberate act;
`GET /health` is the cheap one, and it reports which degraded mode the service
is in rather than merely saying "ok".

### Where job status lives (`jobstore.py`, `migrations/`)

`{job_id}.job-status.json` on a Volume is still the default. Postgres is built
and tested but not switched on -- Neon does not exist yet.
`STEPWISE_JOB_BACKEND=postgres` selects it; unsetting it rolls back. Nothing
above the HTTP boundary can tell the difference, which is the point.

```sh
docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=stepwise postgres:16
DATABASE_URL=postgresql://postgres:stepwise@localhost:5433/postgres python3 migrate.py
DATABASE_URL=… python3 -m pytest test_schema.py -q      # 12 tests
```

Endpoints: `POST /clips` (multipart upload -> dispatches, returns `job_id`
immediately), `POST /clips/link` (paste a TikTok/YouTube URL -- see below),
`GET /jobs/{job_id}` (poll -- the real job-status.schema.json
document, unmodified), `GET /jobs/{job_id}/result` (once succeeded -- the
assembled, schema-validated `MotionResult`), `POST /jobs/{job_id}/retry`
(only for `retryable: true` failures), `GET /assets/{asset_id}` (resolves a
`source_video.asset_id` / `AnimationRef.glb_asset_id` to bytes),
`POST /lessons/{clip_id}/removal` (the takedown path -- see below).

Both `POST /clips` doors answer **429** with `Retry-After` and
`{"detail": {"error": {"code", "message", "retryable": true}}}` when a request
that would start a GPU run is over its limit: 5/hour and 20/day per client IP,
200/day overall (`STEPWISE_LIMIT_IP_HOUR`, `_IP_DAY`, `_GLOBAL_DAY`). A dedupe
hit is never charged. Counted in Postgres `events`, IPs hashed with a daily salt
(`STEPWISE_IP_SALT`, else `DATABASE_URL`); on the Volume backend the limits are
off and the log says so. See ratelimit.py.

## The floor solve (`grounding.py`)

Pure numpy, no GPU, no Modal. `api.py` calls it once per clip to fill
`MotionResult.grounding`. Two swappable seams — `detect_foot_contacts`
(which samples are contact evidence, as weights in [0,1]) and
`fit_floor_plane` (weighted RANSAC) — plus `solve_grounding`, which owns the
`grounded`-vs-`none` decision and its thresholds. A learned foot-contact model
drops in as `solve_grounding(..., contact_detector=...)`.

```sh
python3 -m pytest test_grounding.py -q        # 13 tests, no GPU
python3 grounding.py /path/to/clip.npz        # measure one real clip
```

It reports `none` far more often than you would expect, and
`docs/GATE-REPORT.md`'s grounding addendum explains exactly why with numbers —
read it before assuming the solve is broken.

`camera_intrinsics_from_clip()` also lives here: the clip's real focal length
plus the pinhole model that was verified against real output at 0.00 px
reprojection error. `api.py` uses it for `camera.intrinsics`, replacing a
placeholder that was 12.8% off.

**If you are picking up world placement** (making the dancer travel instead of
dancing in place — OPEN-DECISIONS E6), start from `GroundingResult.evidence`.
It carries the fitted plane, per-frame per-foot contact weights, the contact
points and the foot visibility mask, and it is populated **even when the
verdict is `none`** — which is every real clip so far. Read E6 and the
addendum's world-placement section first: three plausible approaches were
already tried and measured, and the reason they failed is not the one you would
guess.

See `api.py`'s module docstring for the object-storage decision (Modal
Volumes, not S3) and the known scope boundary in `motion_result.py`
(per-joint visibility/suppression and true world-space root placement are
Milestone A/W9 work, not built here).

## Paste a link (`ingest.py`, `POST /clips/link`)

The MVP's front door. Needs the `yt-dlp` binary on PATH (`uv tool install yt-dlp`),
and is given **no credentials of any kind** -- no cookies, no `--netrc`, no
browser cookie import. A platform that demands a login gets a refusal.

```sh
STEPWISE_INVITE_CODES=pilot-w12 .venv/bin/python -m uvicorn api:app --port 8811

curl -X POST localhost:8811/clips/link \
  -H 'Content-Type: application/json' -H 'X-Invite-Code: pilot-w12' \
  -d '{"url":"https://www.tiktok.com/t/ZP83Enx4b/"}'
```

**Read `docs/research/link-ingestion.md` before changing any of this.** Both
platforms' terms prohibit automated downloading. This is scoped to the
invite-only W12 pilot and is not cleared for public launch; `docs/TASKS.md`
carries the tripwire. **Closed by default** -- with `STEPWISE_INVITE_CODES`
unset the endpoint refuses everything. File upload is not gated.

Three things worth knowing:

- **Normalisation is yt-dlp's `(extractor, id)` pair**, not a URL regex. A
  share link, the full `@user/video/...` URL and a tracking-parameter variant
  all resolve to one `source_key`, so pasting the same video twice in any two
  forms lands on one lesson.
- **`clip_id` is derived from that key**, not minted. That is what stops two
  simultaneous pastes of one link becoming two lessons when the index lookup
  loses the read-after-write race. The trade -- the lesson link is computable
  from the source URL -- is in that document's §7a and is a D5 dependency.
- **Refusals happen before the download where they can.** yt-dlp's metadata
  carries `duration` and `live_status`, so an over-length video or a live
  stream costs one ~1.5 s metadata request and no transfer.

Failure codes are mapped in `ingest.classify_fetch_error`, which only names a
reason it can actually observe: TikTok returns "your IP address is blocked" for
a video id that never existed, and YouTube returns "This video is unavailable"
for both a private video and one that never existed, so neither is relayed as a
cause. Anything unclassifiable becomes `fetch_failed` and says the fetch failed,
not why.

```sh
python3 -m pytest test_ingest.py -q           # 20 tests, no network
STEPWISE_LIVE=1 python3 -m pytest test_ingest.py -q   # + 3 that hit TikTok
```

## Dedupe, retention, and removal

Three connected things, added together because they only work together.

**Dedupe on upload** (`fingerprint.py`). Every upload is fingerprinted before
a GPU is spawned; if this dance is already reconstructed, the existing lesson
is handed back and nothing is dispatched. Needs the `ffmpeg`/`ffprobe`
binaries; without them it falls back to exact-sha256 matching and logs that it
did. Catches re-encodes, fps changes, rescales, brightness shifts and ~5%
crops; does not catch a 10%-per-side crop, and deliberately does *not* match a
mirrored clip (left and right matter in a dance) or a trimmed one. Thresholds
are measured, not guessed -- the numbers are in the module docstring and the
measurement is re-runnable:

```sh
mkdir -p /tmp/fpclips
modal volume get stepwise-eval /solo-01.mp4 /tmp/fpclips/solo-01.mp4   # and solo-02, solo-07, group-synced-01
STEPWISE_FP_CLIPS=/tmp/fpclips python3 -m pytest test_fingerprint.py -s
```

**Retention** (`retention.py` + `modal_app.sweep_expired`). Lessons expire
`retention.TTL_DAYS` (180) after they were last opened. The sweeper runs daily
and also reaps npz files whose MotionResult has been materialised. Inspect
before trusting it:

```sh
modal run modal_app.py::sweep_expired --dry-run
```

**Removal** (`POST /lessons/{clip_id}/removal`). Deletes the video, every GLB,
the MotionResult, the manifests, the job records and the fingerprint -- **on
both the Volumes and R2** -- and leaves a tombstone so the link answers 410
Gone. Immediate, not queued. Verified against the live service on 2026-09-21:
9 Volume paths plus 3 R2 keys removed, nothing left in the bucket holding that
lesson, and `/jobs`, `/assets/video:` and `/assets/*.glb` all 410.

One thing that is **not** handled and will matter the day a custom domain
exists: deleting the origin object does not delete the CDN's edge copy. See
`retention._delete_r2_objects` and `docs/DEPLOYMENT.md` §5.2.

```sh
python3 -m pytest test_retention.py -q
```

**The npz is no longer the storage cost it was.** `export_clip_gltf` now
materialises the `MotionResult` once and stores it gzipped, so `api.py` stops
rebuilding it from the npz on every request and the sweeper can delete the
npz. Combined with dropping `pred_vertices`/`expr_params` at write time
(`tools/process_clip.py`), a solo lesson went from **63.93 MB to 4.12 MB**,
measured on solo-01. Details and the retention reasoning: `docs/OPEN-DECISIONS.md`
D6/D7.
