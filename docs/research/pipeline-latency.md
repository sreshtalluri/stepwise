# Pipeline latency: where a lesson's 3.5–7 minutes go

Research only. No production code, config or deploy was changed for this. The
one ask was: "the videos take a very long time to get to lesson state, find
where we can parallelize or optimize."

**Sources, all read-only.**
- `modal app logs stepwise-motion` with `--timestamps --show-container-id`.
  Every stage boundary below is a real log line, at one-second resolution.
- `{clip}.performance.json`, `{clip}.detections.json` and the export manifests on
  the `stepwise-results` Volume.
- Neon `events`: the `dispatch`, `job_created` and `job_finished.wall_s` rows.
- The code path: `api.py::_store_and_dispatch` → `modal_app.run_clip` →
  `vendor/fast-sam-3d-body/tools/process_clip.py` → `modal_app.export_clip_gltf`
  → `_publish_to_r2`.

No GPU job was run for this pass. Every number comes from jobs that users or
operators had already run.

---

## 0. Headline

1. **Reconstruction is the largest single stage, but it is not most of the
   wait on short clips.** It takes 56–63 % of wall time on 35–48 s clips and
   39–46 % on 12–14 s clips. Every job also pays about **90–110 s of fixed
   overhead** that has nothing to do with clip length:
   - GPU cold start: ~10 s
   - model load: ~22 s, including two internet downloads on every cold start
   - smoothing and save: 12–35 s
   - a second GPU container for export: 5–30 s
   - R2 publish: 4–13 s
2. **The export step asks for an L40S but does no GPU work.** Once, this cost
   **286 s** of a 436 s job (a106): the step waited for GPU capacity, and
   `run_clip` held its own L40S idle the whole time. Normally it costs a 5–30 s
   second cold start.
3. **Reconstruction runs one frame at a time, in fp32 eager mode, with no CPU
   reservation.** The fast paths that give Fast-SAM-3D-Body its name are
   vendored but switched off: `USE_COMPILE`, `LAYER_DTYPE=bf16` and the CUDA
   graphs are all env-gated with default off. The two decoders take about half
   of each 0.26 s forward pass. Per-frame speed also varies from 0.34 to 0.6 s
   between identical runs, which looks like CPU starvation.
4. **The reconstruction pass has no temporal dependency.** Detection and track
   hygiene run first, over the whole clip. After that, each frame is
   reconstructed independently, and smoothing runs afterwards on the full
   track. So the pass can be batched across frames, or split across GPUs by
   time window, **with no overlap and no stitching.**

---

## 1. The critical path, as the code runs it

```
POST /clips or /clips/link  (web, CPU, min_containers=0)
  link only: yt-dlp probe → dedupe → yt-dlp download
  fingerprint → Volume batch_upload → R2 video publish
  → jobstore dispatch row → spawn propose_counts (CPU) + spawn run_clip (L40S)
run_clip (L40S, cv_image, no cpu=, default scaledown)
  imports → load SAM-3D-Body (2.0 GiB ckpt) + MHR (664 MiB)
            + torch.hub dinov3 zip from GitHub + RTMO onnx zip from openmmlab
  ffmpeg → JPEG frames at 15 fps
  pass 1: RTMO + ByteTrack, one frame at a time → track hygiene
  pass 2: SAM-3D-Body process_one_image, one frame (B=1) at a time
  bone constraint → hand/foot crops → Kalman smoothing (CPU, Python loop)
  save npz → performance.json → wait on propose_counts
  export_clip_gltf.remote()   ← blocks, holding the L40S
export_clip_gltf (L40S requested, gltf_image, CPU-only work)
  load npz → per-track GLB (pymomentum) → region split → LINEAR rewrite
  → MotionResult.json.gz → R2 publish (sequential puts)
run_clip writes job-status "succeeded" → client poll (2 s) sees it
```

`propose_counts` is already parallel and is never on the critical path. Counts
are ready 17–55 s after the request, which is before the model has even loaded.

---

## 2. Measured waterfalls

t=0 is when the request arrives. Seconds.

- For uploads, t=0 is `POST /clips` end time minus its duration.
- For the link job, t=0 is `POST /clips/link` end time minus its duration.

"GPU start" runs from the spawn to the first `[job-status] queued` write, and
it includes Python imports. "Export start" runs from `Building the 3D body
file` to the export container's first line.

| job | clip | Ingest | GPU start | Model load | Detect | **Recon** | Post+smooth | Export start | Export | R2+status | **Total** | recon % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dc32 | 44.7 s TikTok link, 671 fr, 1 dancer | 47 | 10 | 22 | 41 | **238** | 34 | 14 | 8 | 8 | **422** | 56 % |
| 5716 | 47.7 s upload, 715 fr, 1 dancer | 20 | 13 | 21 | 41 | **246** | 35 | 5 | 4 | 4 | **389** | 63 % |
| 345b | 35.4 s upload, 531 fr, 4 tracks* | 13 | 9 | 22 | 25 | **155** | 23 | 3 | 11 | 13 | **274** | 57 % |
| a106 | 13.1 s upload, 196 fr, 1 dancer | 15 | 10 | 21 | 14 | **71** | 12 | **286** | 3 | 4 | **436** | 16 % |
| 7995 | 12.0 s upload, 180 fr, 1 dancer | 12 | 15 | 25 | 28 | **96** | 17 | 8 | 3 | 5 | **209** | 46 % |
| b822 | 14.4 s upload, 216 fr, 4 tracks* | 13 | 11 | 20 | 13 | **76** | 14 | 30 | 8 | 11 | **196** | 39 % |

\* This run predates today's track hygiene. It reconstructed and exported four
tracks for what is one real dancer.

The totals agree with Neon `job_finished.wall_s` to within the client's polling
lag: dc32 392, 5716 409, 345b 281, a106 439, 7995 209 and b822 205, all
measured from `dispatch`. That measurement starts after ingest, so for the link
job it undercounts by the ~33 s spent on the link fetch.

The interactive waterfall was rendered and checked in the built-in browser. It
lives outside the repo, so its source is not committed; the table above carries
the same data.

### What the stages are made of

- **Ingest.**
  - The link job took 43 s in total. 35 s of that was execution: two
    sequential yt-dlp invocations (probe, then download), fingerprint, Volume
    upload and the R2 video put. The other ~8 s was the `web` container's own
    cold start, because it runs with `min_containers=0`.
  - Uploads took 7–16 s, including the browser transfer.
- **GPU start (≈10 s).**
  - The L40S container is up 4–10 s after the spawn. The image is the large
    CUDA-devel one.
  - The first status write follows 2–7 s later, and model code starts 8 s
    after that, on torch and sam_3d_body imports.
  - Only once did a job wait for GPU capacity, and that was an export (see
    a106).
- **Model load (20–25 s).** This happens on every job, even on a warm
  container, because `load_sam_3d_body` runs inside `process_clip`. It covers:
  - the 2.0 GiB checkpoint and 664 MiB MHR, read from the weights Volume
  - `torch.hub` downloading `facebookresearch/dinov3/zipball/main` from GitHub
  - rtmlib downloading the RTMO onnx zip from `download.openmmlab.com`

  Both downloads happen on every cold start, which is also a reliability risk.
  If GitHub or openmmlab goes down, every job fails.
- **Detect (13–41 s).** ffmpeg takes 2–3 s. RTMO+ByteTrack then runs one frame
  at a time at ~15–20 fps, which is slow for RTMO-m on an L40S.
- **Recon (0.34–0.6 s per frame, 1.7–3.4 fps).** One sampled dc32 frame breaks
  down like this:
  - body backbone: 35 ms (B=1, 512²)
  - body decoder: 57 ms
  - hand backbone: 38 ms (B=2)
  - hand decoder: 62 ms
  - IK post-process: 15 ms
  - total inside `process_one_image`: 0.257 s
  - outside the model, the loop spends another ~0.08 s on `cv2.imread` and on
    roughly 45 debug log lines per frame
  - peak VRAM is **3.7 GB of 48 GB**

  The same code ran 7995 at 0.54 s/frame, with recurring ~10 s stalls, and
  dc32 at 0.35 s/frame. That spread fits a CPU-starved, kernel-launch-bound
  loop: `run_clip` sets no `cpu=`, so it gets Modal's small default
  reservation.
- **Post+smooth (12–35 s).**
  - Bone constraint and crops take about 1 s.
  - `smooth_clip_result` takes 6–31 s. It steps 127 joints × 3 axes = 381
    scalar filterpy `KalmanFilter`s per frame in Python, so a 671-frame clip
    means ~250k predict/update calls.
  - Saving the npz and committing takes 2–5 s.
- **Export start (3–30 s, plus one 286 s outlier).** This is a second L40S
  container.
  - When it is reused warm, as for 345b and 5716, it takes 3–5 s.
  - Cold, it took 8–30 s.
  - On a106, Modal logged *"waiting to be scheduled on a GPU_L40S worker"*,
    and the step waited 286 s.
  - The function does no CUDA work: the MHR basis loads with
    `map_location="cpu"`, and the pymomentum save and pygltflib rewrites run on
    the CPU.
- **Export and R2 (7–24 s).** GLB writing takes 3–11 s, depending on the number
  of tracks. The R2 puts run one after another, for 3–12 s in total (345b had 5
  objects).

---

## 3. Ranked opportunities

Estimated savings are in seconds per job:

- **long** means a dc32-like job (45 s clip, 422 s today)
- **short** means a 7995-like job (12 s clip, 209 s today)

Costs use Modal's published on-demand rates as of 2026-09: L40S $1.95/h, H100
≈$3.95/h, CPU ≈$0.05 per core-hour. Check these against modal.com/pricing
before relying on them.

| # | Change | Saves (long / short) | Cost impact | Risk | Effort |
|---|---|---|---|---|---|
| 1 | **Export on CPU, and stop `run_clip` blocking its L40S on it.** Drop `gpu=` from `export_clip_gltf` (smoke-test that `pymomentum-gpu` imports without a GPU, or pin `pymomentum-cpu`). Have `run_clip` spawn export and return, or let export write `succeeded` itself. | 10–25 s typical; **removes the ~5 min GPU-queue tail** | Cheaper: no second L40S, and no idle L40S while export runs or queues (a106 burned ~$0.16 idle) | Low–med (pymomentum import on CPU) | S |
| 2 | **Load models once per container, and stop downloading at runtime.** Move the model load into `@app.cls` + `@modal.enter`. Bake the dinov3 hub repo and the RTMO onnx into `cv_image`. | 5–8 s cold, **~22 s on every warm reuse** | None | Low | S |
| 3 | **Overlap ingest with the GPU cold start.** Spawn `run_clip` when the POST arrives. It loads the model, then polls for the video; the load order in `process_clip` already fits. Cancel the `FunctionCall` if ingest refuses the clip (dedupe, too long, rate limit). | long ~35 s, short ~10 s (up to the ~40 s of GPU start + load) | ≈$0.02 wasted per refused or abandoned request | Low–med (cancel paths) | S–M |
| 4 | **Enable the vendored fast paths.** `USE_COMPILE=1 COMPILE_MODE=reduce-overhead LAYER_DTYPE=bf16` (optionally `MHR_USE_CUDA_GRAPH=1`) via `.env()` on `run_clip`. | recon 1.5–3× → **long 80–160 s, short 30–60 s** | Cheaper per job, but compile warmup adds ~30–60 s per **cold** start (GATE-REPORT saw ~30 s), so pair it with #2 plus a memory snapshot, or a warm window | Med: bf16 accuracy must be re-checked on the eval clips (solo-01/02/07, group-synced-01) | S to flip, M to validate |
| 5 | **Reserve CPU and remove per-frame debug logging.** Set `cpu=4` (or 8) and `memory=` on `run_clip`. Gate the vendor's unconditional `[process_one_image]`/`[forward_pose_branch]`/IK-box prints (~45 lines per frame, ~30k lines per job; Modal's log API returned at most ~11k lines per window). | recon 10–40 % plus faster smoothing and detect; **measure first** | +$0.01–0.04 per job | Low | S |
| 6 | **Vectorise smoothing.** The 381 independent 2-state constant-velocity Kalman filters become numpy arrays stepped together (same equations), checked against `test_smoothing.py` outputs. | long ~29 s, short ~5 s | None | Low–med (numerical equivalence) | M |
| 7 | **Batch reconstruction across frames.** Pass 2 knows every box up front. Feed 8–16 frames' crops per forward, since the multi-person path already batches crops, and prefetch/decode JPEGs in a thread. | recon 2–4× on top of #4 (long 100–150 s) | Cheaper per job | Med (adapter over `process_one_image`; cam intrinsics are per-image but identical in a clip) | M–L |
| 8 | **Show the lesson before the 3D is ready.** The video is on R2 at dispatch, and counts arrive by t≈17–55 s. Open the lesson in video+counts mode (the loop, speed and count tools all work) and swap in 3D when `succeeded` lands. | **Perceived wait goes from 3.5–7 min to under 1 min**; real pipeline unchanged | None | Med (product/UX: lesson page must tolerate no MotionResult) | M |
| 9 | **Overlap detection with model load** inside `run_clip`: ffmpeg + RTMO in a thread while SAM-3D-Body loads (VRAM is ample). | ~20 s | None | Low | S |
| 10 | **Split reconstruction across GPUs by time window.** Detection and hygiene run once, then `run_recon_chunk.map()` over N frame ranges, concatenating `per_frame` before smoothing. No overlap or stitching is needed (see headline 4). | long 238 s → ~60–80 s at N=4 (plus one extra cold start in parallel); short: nothing | GPU-seconds about the same, plus N × (start+load) ≈ $0.02 per chunk cold; only worth it with #2/#3 or snapshots | Med (npz plumbing, Volume hand-off) | M–L |
| 11 | **Cold start: memory snapshots.** `enable_memory_snapshot=True`, with the model loaded to CPU in `@modal.enter(snap=True)` and moved to GPU after restore, or Modal's experimental GPU snapshot. | 15–25 s per cold start; makes #4's compile warmup affordable | None | Med (snapshot + CUDA/compile interaction) | M |
| 12 | **Warm GPU.** Options: `min_containers=1`; a business-hours schedule via `update_autoscaler`; or `scaledown_window=600–900`. | ~30–40 s per job that lands warm (all of GPU start + load, once #2 is in) | 24/7: **~$1,424/month** (730 h × $1.95). 12 h/day: ~$712/month. scaledown 15 min: at most ~$0.49 idle per burst. Per-job cold overhead is only ~$0.02, so 24/7 warm breaks even at ~60k jobs/month | Low | S |
| 13 | **Publish to R2 in parallel** (thread pool over `put_file`), and merge the two yt-dlp calls into one (`--print-json` during the download). | R2 2–9 s; link ingest a few s | None | Low | S |
| 14 | **Lower the sample rate adaptively**, for example 10 fps above 30 s (the GLB already interpolates LINEAR). Or use `IMG_SIZE=384` for the backbone. | recon −33 % (10 fps) | Cheaper | **High for dance quality**: fast footwork and hands. Last resort | S |
| 15 | **Faster GPU (H100 vs L40S).** The current loop is B=1 and launch-bound, so an H100 would likely give ~1.2–1.5× at ~2× the price. After #4/#7 the work becomes compute-bound, and H100 might reach ~2× and roughly break even. Separately, a GPU fallback list (`gpu=["L40S", "A100-80GB", "L4"]`) protects against capacity queues. VRAM is only 3.7 GB, so an L4 ($0.80/h) fits as the fallback. | Uncertain; benchmark after #4/#7 | ≈ +100 % $/h | Low | S to try |
| 16 | **Run detection on a cheaper GPU or CPU.** It is upstream of reconstruction, and hygiene needs the whole clip. Moving it off-box only adds a hand-off; #9 captures the overlap for free. | ~0 | – | – | Not recommended |
| 17 | **Write the GLB during reconstruction.** Export needs the full timeline and a whole-track median shape, so there is little to overlap. #1 plus #13 take most of the export tail. | <5 s | – | – | Not recommended |

### What the top items add up to

For a 45 s clip like dc32 (422 s today):

| After | Total |
|---|---|
| #1 + #2 + #3 + #9 | ≈ 330 s |
| + #5 + #6 | ≈ 280 s |
| + #4 at 2× | ≈ 160 s |
| + #7 | ≈ 110–130 s |

With #8, the learner is in the lesson in under a minute either way.

For a 12 s clip like 7995 (209 s today):

| After | Total |
|---|---|
| #1–#3 + #9 | ≈ 150 s |
| + #4–#6 | ≈ 90 s |

These are estimates built from the measured stage times. Nothing was re-run.

---

## 4. Top three recommendations

1. **Take the GPU out of export, and free `run_clip`'s L40S before export runs
   (#1).** It is small, it saves 10–25 s on every job, and it removes the
   multi-minute capacity tail entirely. It also cuts cost.
2. **Remove the per-job fixed overhead (#2 + #3 + #9).** That means:
   - model load moved into `@modal.enter`
   - the dinov3 and RTMO downloads baked into the image
   - `run_clip` spawned the moment the POST arrives, so the GPU cold start and
     model load run during the 7–43 s ingest
   - detection overlapped with model load

   Together that is about 40–70 s per job with no standing cost. It beats the
   ~$1,424/month of an always-on L40S at beta volume.
3. **Make reconstruction fast (#4 → #5 → #7), and show video+counts first
   (#8).**
   - Flip the vendored compile/bf16 flags behind an eval-clip accuracy check,
     and reserve CPU.
   - Then batch frames. Reconstruction is 56–63 % of a long clip, and the
     model is currently run in its slowest configuration.
   - In parallel, open the lesson on video+counts while the 3D finishes. That
     is the only change that brings perceived wait under a minute without
     touching the GPU at all.

## 5. Measurement gaps worth closing (cheap)

- `performance.json` records only reconstruction fps, peak VRAM and a
  `cost_usd`. That cost is `process_clip` wall time × $1.95/h, so it leaves out
  container start, the export wait and idle hold time. Stage timestamps (load /
  detect / recon / smooth / export / publish) written into the same file would
  make this waterfall a query instead of a log-scrape.
- `job_finished.wall_s` starts at `dispatch`. For link jobs that misses the
  ~35 s fetch, and it includes client polling lag (its own docstring says as much, in
  `analytics.record_finished`). A worker-written finish time plus a
  request-arrival time would close both gaps.
- Modal's log API returned only ~11k lines per query window because of the
  per-frame debug prints. That is why this doc samples frame-level timings
  rather than reading all of them. Item #5 fixes it too.
