# Infrastructure — architecture decision record

**Written 2026-09-20.** Branch `research-infrastructure`, cut from `w4-jobservice`.
Research only: nothing was deployed, provisioned or built. Every price below carries
a source and a retrieval date, because pricing pages move and a stale number is
worse than no number. Anything unverified is marked **[UNVERIFIED]** and says why.

Constraint from the builder, taken as binding: *no Vercel, no "easy now, expensive
later" default path.* The test applied throughout is not "what is cheapest this
month" but "which line items grow with success, and can I leave if I'm wrong."

---

## 0. Summary — the decisions

| # | Decision | Recommendation | The single strongest reason |
|---|---|---|---|
| 1 | API hosting | **Modal `@modal.asgi_app`** | `api.py` already holds Modal Volume and Function handles; hosting it on Modal collapses two credential sets into one and costs $0 at idle — and because it is plain FastAPI, leaving costs a day. |
| 2 | Database | **Neon Postgres (Launch), pooled connection string** | Scale-to-zero pay-as-you-go means a real Postgres costs ~$3/mo at 100 lessons and still under $40 at 10,000 — and the exit is `pg_dump`. |
| 3 | Object storage + delivery | **Cloudflare R2 behind a custom domain** | Zero egress fees removes the one line item that grows with success from the P&L permanently; a 100× traffic spike costs $0 more in bandwidth. |
| 4 | Job state / queue | **Postgres row as source of truth; keep HTTP polling** | The `job-status.schema.json` document and `ProcessingScreen.tsx` keep working byte-for-byte; only the storage behind the endpoint changes. |
| 5 | Frontend hosting | **Cloudflare Workers via `@opennextjs/cloudflare`** | The app needs exactly two server features (same-origin `/api` proxy, per-lesson OG tags); Workers gives both, on the same account as R2, with free static-asset serving — and `next start` in a container is a one-day fallback if the adapter ever breaks. |
| 6 | Secrets / CI / observability | **Modal Environments + GitHub Actions + Sentry free + Better Stack free** | All four are free at this scale and none of them is a platform you have to stay on. |
| 7 | Scale arithmetic | **GPU dominates at every modeled scale** | At 100 / 1,000 / 10,000 lessons per month GPU is 57% / 85% / 91% of the bill. Egress is $0 at all three *because* of decision 3. |

**Finding that contradicts the brief's premise.** The brief assumes "egress, not compute,
is the cost that grows." Under the measured numbers that is **not true at any scale
modeled here** — GPU reconstruction dominates throughout. Egress would dominate only on
a per-GB-egress provider (S3/CloudFront/Supabase/Railway service egress), or once the
`caching-retention` dedupe index makes GPU cost collapse while views keep growing.
Decision 3 is therefore a *risk* decision, not a cost decision at today's volume: you
are buying the removal of an unbounded line item, not a saving. That is still the right
buy, and the reasoning should be recorded honestly rather than dressed up as a saving.

---

## 1. What exists today (verified by reading the branch — do not redesign)

- **Modal GPU layer works and was expensive to get working.** Seven separate environment
  bugs (`docs/GATE-REPORT.md` G3), two deliberately incompatible images because
  `pymomentum` needs Python 3.12/3.13 + torch 2.8 while the CV stack is pinned to Python
  3.11 + torch 2.5.1 + cu124. Measured: **$0.058 per 19.7 s clip, 291/296 frames (98.3%),
  3.79 fps, 3.69 GB peak VRAM on L40S.** Treat these images as load-bearing; every
  recommendation below avoids touching them where possible.
- **`services/motion-api/api.py` is a working FastAPI service, deployed nowhere.** It
  deliberately has no CUDA/torch dependency (`requirements-api.txt` is fastapi + uvicorn +
  modal + numpy + jsonschema + pydantic). It uploads to a Volume, `.spawn()`s `run_clip`,
  polls a JSON file, assembles `MotionResult`, and proxies asset bytes.
- **Storage is four Modal Volumes**: `stepwise-weights`, `stepwise-eval`,
  `stepwise-results`, `stepwise-uploads`.
- **Job status is a JSON file on a Volume.** `modal_app.py::run_clip::write_status` writes
  `{job_id}.job-status.json` and calls `results.commit()`. The code's own comment flags
  this as provisional.
- **There is no database at all.** No users, no sessions, no job records, no dedupe index.
- **`apps/web`** (on `w7-marketing` / `w5-viewer`): Next.js 16.3.5, React 19.2.0, R3F 9.7.0,
  three 0.186.0. Marketing, upload and job pages are **all `"use client"`**. The lesson
  page is an async server component that reads a fixture off disk with
  `generateStaticParams` — a build-time stand-in for a real API call. Client code fetches
  same-origin `/api/jobs/...` and `/api/jobs` (POST). There is no `app/api` route in the
  tree, so a rewrite or proxy is assumed but not yet written.
- **R2 credentials already exist locally** at `~/.stepwise-secrets/r2.env`. Decision 3
  is therefore a smaller step than it looks.

### Measured and assumed workload shape

| Artifact | Size | Source |
|---|---|---|
| Source video (19.7 s, 576×1024) | ~2 MB | `evaluation/clips.yaml` notes TikTok serves 576×1024, not 1080p |
| Source video (60 s cap) | **5 MB assumed** | extrapolated from the above; no 60 s clip measured |
| `MotionResult` JSON, 1 dancer | **~1.1 MB assumed** (brief) | repo fixtures are 1.9 MB raw / 31 KB gzipped, but they are *hand-built* with repeated identity quaternions and do not represent real float data — see "could not verify" |
| GLB, per dancer | **~1.5 MB assumed** (brief) | the only measured GLB in the repo is the 589 KB neutral-pose smoke test (`GATE-REPORT.md` G6), which is one repeated frame |
| `.npz` intermediate | **58.3 MB** (brief) | the single biggest object, and an intermediate — see §3 |
| GPU time | 2–4 min per clip | `docs/OPEN-DECISIONS.md` A1 |

**Delivered payload per lesson view = video 5 MB + GLB 1.5 MB + JSON 1.1 MB ≈ 7.6 MB.**
That is the number every egress calculation below uses.

---

## 2. Decision 1 — API hosting: Modal `asgi_app`

### Recommendation

Deploy `api.py` as a Modal ASGI app in the same `stepwise-motion` app, in a Modal
Environment named `prod`, with a second Environment named `staging`.

```python
# sketch only — not built
@app.function(image=api_image, secrets=[modal.Secret.from_name("stepwise-db")])
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    from api import app as fastapi_app
    return fastapi_app
```

### Why, over the alternatives

`api.py` is *already* a Modal client. It constructs `modal.Volume.from_name(...)` at import
time and calls `modal.Function.from_name(APP_NAME, "run_clip").spawn()`. Running it anywhere
else means a second platform, a second deploy pipeline, and a Modal API token sitting in
someone else's secret store. Running it on Modal means one account, one `modal deploy`, one
set of credentials, and the Volume/Function handles become in-cluster rather than
authenticated round trips from outside.

Cost at idle is the second reason. Modal bills per second of container time and scales to
zero by default; `scaledown_window` defaults to **60 seconds** ([Modal scaling docs /
corroborating sources, retrieved 2026-09-20] — the official page documents the parameter but
the default is not printed on it, see "could not verify"). CPU is **$0.0000131 per physical
core-second (~$0.047/core-hour)** and memory **$0.00000222 per GiB-second (~$0.008/GiB-hour)**
([modal.com/pricing, retrieved 2026-09-20]). A 1-core / 2 GiB API container therefore costs
about **$0.063/hour while it is actually serving**, and $0 the rest of the time. The Starter
plan includes **$30/month of free compute** and costs $0/month.

The third reason is the one that actually matters for a "strong foundation": **the decision
is reversible in a day.** `api.py` is a plain FastAPI app with no Modal-specific web code. If
Modal-as-a-web-host turns out wrong, `uvicorn api:app` runs on Railway, Fly or a Hetzner box
unchanged. Choosing the tightly-coupled option is only defensible because the coupling is
one decorator deep.

### What was considered and rejected

| Option | Price (retrieved 2026-09-20) | Why not |
|---|---|---|
| **Railway** | Hobby $5/mo (incl. $5 usage), Pro $20/mo per workspace; ~$10/GB-RAM-month, ~$20/vCPU-month; **egress $0.05/GB** | Excellent DX and a genuinely good fallback. Rejected only because it is a second platform for a service that is 90% Modal control-plane calls. The $0.05/GB service egress is also a trap if you ever proxy assets again. |
| **Fly.io** | shared-cpu-1x 512 MB ≈ **$3.19/mo**; egress **$0.02/GB** (NA/EU); volumes $0.15/GB-mo | Cheap and boring. Rejected for the same "second platform" reason; also Fly's operational model (Machines, `fly deploy`, regional placement) is more surface area than a solo builder needs for one stateless Python process. |
| **Hetzner Cloud VPS** | CPX11 (2 vCPU / 2 GB) from **€4.99/mo** EU with **20 TB** included traffic; overage **€1/TB**; US locations include only 1 TB. Note Hetzner ran a price adjustment 2026-06-15 and the CX line appears to have been superseded — **[UNVERIFIED]**, prices were stripped from the live pages I could reach | The cheapest bandwidth on the list by an order of magnitude. Rejected because you would own TLS renewal, kernel patching, log rotation, backups and a deploy pipeline — for a service whose bill on Modal is under $10/month. Buying $50/month of unused bandwidth with $500/month of your own time is the wrong trade *today*. Revisit at 100× (§8). |
| **AWS (ECS/App Runner/Lambda)** | n/a | Rejected outright: highest operational burden per unit of value, and its egress at $0.09/GB is the exact cost curve this document is trying to avoid. |

### Honest costs of this choice

- **Cold start.** First request after idle boots a container — "might take a few seconds"
  ([modal.com/docs/guide/webhooks, retrieved 2026-09-20]). For an upload endpoint this is
  invisible; for the 2-second job poll it is invisible after the first tick. Mitigate with
  `min_containers=1` only if a real user complains — that pins ~$45/month of always-on
  container and should not be paid speculatively.
- **Workspace rate limit** is 200 function calls or HTTP requests per second with a
  5-second burst multiplier; over that you get 429s. Comfortable at every scale in §7.
- **Starter plan ceilings**: 100 containers, 10 GPU concurrency, **1 day of log retention**,
  200 deployed apps. The log retention is the one that hurts — see §6.
- **Vendor concentration.** GPU, API and object-storage-of-record all on Modal is one
  account away from total outage. Decision 3 (assets on R2) already halves this; the
  database on Neon quarters it. Accept the rest.

---

## 3. Decision 3 — object storage and delivery: Cloudflare R2

Taking this before the database, because it is the decision the brief cares most about and
because it changes what the database has to store.

### The problem with Modal Volumes as a delivery layer

Not cost. Modal Volumes are **$0.09/GiB-month including 1 TiB/month free**, and Modal charges
**no egress or bandwidth fees at all** ([modal.com/pricing, retrieved 2026-09-20]). On pure
dollars, Volumes beat R2 until you store more than a terabyte. The problems are architectural,
and there are four:

1. **No HTTP range requests.** `api.py::_volume_read_bytes` calls
   `volume.read_file_into_fileobj(path, buf)` — it reads the whole object into memory and
   returns a single `Response`. A `<video>` element asking for `Range: bytes=…` gets a 200
   with the full body. The learner scrubbing the video (the core interaction in `DESIGN.md`
   §7c: *"the learner's own clip plays immediately… speed, mirror and loop already working"*)
   downloads the entire clip before the first seek resolves. This is a product defect today,
   not a scaling problem for later.
2. **Every byte crosses the Modal control plane twice.** Volume reads go through Modal's
   client library, not a raw HTTP GET. The bytes travel Volume → API container → browser.
3. **No CDN, no edge cache, no immutable URLs.** A learner who loops a lesson twenty times
   should pull the GLB once and hit `Cache-Control: public, max-age=31536000, immutable`
   thereafter. Through a Python proxy you are re-reading and re-serializing every time unless
   you hand-roll ETags.
4. **Each in-flight stream occupies a container concurrency slot**, competing with job
   dispatch and status polling for the same 100-container Starter ceiling.

### Recommendation

Move delivered artifacts — source video, GLB, `MotionResult` JSON — to an **R2 bucket exposed
through a custom domain** (e.g. `assets.<domain>`), not the `r2.dev` URL. Keep the `.npz` and
the model weights on Modal Volumes: they are pipeline-internal, never touched by a browser,
and the Volumes already work.

`api.py`'s contract does not change. `asset_id` stays opaque (the schema comment in `api.py`
is explicit that an `asset_id` is *never* a signed or expiring URL). `GET /assets/{asset_id}`
becomes a **302 to the R2 custom-domain URL** instead of a byte proxy. That is a three-line
change to one endpoint.

### R2 pricing (developers.cloudflare.com/r2/pricing, retrieved 2026-09-20)

| Item | Standard | Notes |
|---|---|---|
| Storage | **$0.015 / GB-month** | Infrequent Access $0.01, 30-day minimum duration |
| Class A ops (writes/lists) | **$4.50 / million** | |
| Class B ops (reads) | **$0.36 / million** | |
| **Egress to internet** | **$0** | via Workers API, S3 API or `r2.dev` |
| Free tier | 10 GB-month storage, 1M Class A, 10M Class B | Standard class only |

Billable units round up (1.1 GB-month bills as 2 GB-month; 1,000,001 ops bill as 2 million).

### Why R2 over the alternatives

| Option | Storage | Egress | Verdict |
|---|---|---|---|
| **Cloudflare R2** | $0.015/GB-mo | **$0** | **Chosen.** Zero egress; custom domain gets real Cloudflare CDN caching (Smart Tiered Cache recommended by the docs); presigned PUT lets the browser upload straight to the bucket; same account as the web host (decision 5) and DNS. |
| **Backblaze B2** | ~$0.00695/GB-mo ($6.95/TB-mo), first 10 GB free | free up to 3× monthly stored bytes, then **$0.01/GB** | Cheapest storage on the list, and materially cheaper than R2 per stored GB. Rejected because the free-egress allowance is a *multiple of stored data* — exactly the wrong shape for this product, which stores little and serves it repeatedly. A viral lesson blows through 3× instantly. Free egress via CDN partners (bunny.net, Fastly, CacheFly) fixes it, but that is a fourth vendor. |
| **S3 + CloudFront** | S3 Standard ~$0.023/GB-mo **[UNVERIFIED from AWS's own page — the pricing table did not render; corroborated by Railway's published comparison table]** | S3→internet **$0.09/GB** (first 100 GB/mo free aggregated across AWS); CloudFront **1 TB/mo free**, then **$0.085/GB** (next 9 TB, US/EU), HTTPS requests $0.010/10k after 10M free | The industry-standard answer and the most expensive one. CloudFront's 1 TB free tier hides the problem until you cross it, at which point every additional lesson view has a marginal bandwidth cost forever. This is precisely the "easy but costs more later" path the builder ruled out. CloudFront also now offers flat-rate plans (Free / Pro $15 / Business $200 / Premium $1,000 per month, no overage) — better, but still a bill that grows, versus zero. |
| **Railway Buckets** | $0.015/GB-mo, **free unlimited egress and free unlimited S3 operations** | $0 | Genuinely competitive on price and beats R2 on operation fees. Rejected on one hard blocker: **"Public buckets are currently not supported."** Access is presigned URLs or proxying through a backend — which reintroduces exactly the byte-proxying problem we are leaving. No CDN. Revisit if Railway ships public buckets. |
| **Stay on Modal Volumes** | $0.09/GiB-mo, 1 TiB free | $0 | Cheapest on paper below 1 TiB. Rejected for the four architectural reasons above, principally no range requests. |

### Licence / terms scrutiny (ground rule 2)

Cloudflare's **Service-Specific Terms for Application Services, last updated 2026-06-02**,
carry a CDN content restriction: Cloudflare "reserves the right to disable or limit access to
or use of the CDN… if you are using the CDN without Paid Services to serve video or a
disproportionate percentage of pictures, audio files, or large files," and states that for
non-Enterprise customers Cloudflare "offers specific Paid Services (e.g., Developer Platform,
Images, Stream) you must use in order to serve video or other large files via the CDN." The
old blanket Section 2.8 was removed in May 2023 and replaced by this CDN-scoped wording.

**This product serves video. Treat that as a live term, not a footnote.**

- The mitigation is to be an unambiguous paid Developer Platform customer: **Workers Paid at
  $5/month** ([developers.cloudflare.com/workers/platform/pricing, retrieved 2026-09-20]),
  which decision 5 buys anyway. Do not run this on the free plan to save $5.
- **[UNVERIFIED]:** the rendering of the terms page I retrieved names "Developer Platform,
  Images, Stream" and does **not** explicitly name R2 as a permitted origin. Cloudflare's
  2023 announcement blog says content hosted by a Cloudflare service (Stream, Images, R2) may
  be served via the CDN; multiple community threads from 2023–2024 record R2-backed video
  being flagged anyway and Cloudflare staff calling it a false positive. **Read the canonical
  terms yourself before public launch, and keep the support-ticket path in mind.** If this
  ever becomes a real block, Backblaze B2 + bunny.net is the escape hatch and R2's S3-compatible
  API makes the migration a `rclone sync`.

No other recommended service has a field-of-use or copyleft problem. Sentry's *server* source
is BSL/FSL-licensed, which is irrelevant because we use the hosted SaaS and are not reselling
it.

### The `.npz` decision (this is a D6 question, and it is worth money)

The `.npz` is **58.3 MB — 88% of everything a lesson produces** — and it is an intermediate:
`export_clip_gltf` reads it to build the GLB, and `api.py::_build_motion_result` reads it to
assemble `MotionResult`. Once `MotionResult` has been assembled and stored, nothing needs it
except a re-export.

**Recommendation: build `MotionResult` once at job completion, store the assembled JSON in R2,
and delete the `.npz` on a 7-day timer.** This turns 65.9 MB/lesson of retained storage into
7.6 MB/lesson — a 8.7× reduction — and has the side benefit of removing a per-request numpy
parse from `GET /jobs/{id}/result`, which today re-derives the whole document on every call.

---

## 4. Decision 2 — database: Neon Postgres

### Postgres, and why not something else

The data is: users (D5), sessions, job records, lesson records, asset records, a retention
timer (D6), a soft-delete flag (D7), and a content-hash → `clip_id` dedupe index (the
`caching-retention` branch). Small rows, modest write volume, one hot read path (job status
polled every 2 s). Uniqueness constraints on the dedupe hash and the share slug; a TTL sweep;
a foreign key from assets to lessons so deletion cascades.

That is a relational workload with integrity constraints and it is small. Postgres is correct
and needs no defending. What *does* need defending is the two tempting non-answers:

- **SQLite on a Modal Volume is wrong here, specifically.** Not because SQLite is weak — it
  would be fine on a single always-on box — but because the API scales to zero and can run in
  several containers at once, and Modal Volumes are commit-based and eventually consistent,
  not a POSIX filesystem with working locks. `modal_app.py::run_clip` already carries a
  `uploads.reload()` workaround with the comment *"this is a Volume, not a queue — no delivery
  guarantee beyond eventually consistent."* Putting a write-ahead log on that substrate is a
  data-loss bug waiting to be discovered at 3am.
- **"Keep using JSON files" is wrong** for the same reason plus the dedupe index: you cannot
  do a unique constraint on a directory.

### Recommendation: Neon, Launch plan, pooled connection string

Neon pricing ([neon.com/pricing and /docs/introduction/plans, retrieved 2026-09-20]):

| | Free | Launch | Scale |
|---|---|---|---|
| Monthly fee | $0 | **pay-as-you-use, no monthly minimum** | pay-as-you-use |
| Compute | 100 CU-hours/project | **$0.106/CU-hour** (up to 16 CU autoscale) | $0.222/CU-hour |
| Storage | 0.5 GB/project | **$0.35/GB-month** | $0.35/GB-month |
| Egress | 5 GB | 500 GB included, then $0.10/GB | same |
| Scale-to-zero | 5 min, cannot disable | 5 min, **can disable** | fully configurable |

1 CU ≈ 4 GB RAM. Scale-to-zero plus no monthly minimum is the whole argument: an idle database
bills nothing, and this database is idle most of the time.

**Single strongest reason:** it is the only managed Postgres on the list that costs
approximately nothing when nobody is using it and is still plain Postgres when 10,000 people
are — and the migration away is `pg_dump`, because you will deliberately use no Neon-specific
feature.

### Rejected, with reasons

| Option | Price (retrieved 2026-09-20) | Why not |
|---|---|---|
| **Supabase** | Free $0 (**projects pause after 1 week idle**, 500 MB DB); Pro **$25/mo** + $10/project compute − $10 credits; 8 GB DB included then $0.125/GB; **egress 250 GB included then $0.09/GB**; storage 100 GB then $0.0213/GB | The strongest *product* case — it would also solve D5 (magic-link auth) for free. Rejected on two counts: the free tier's auto-pause is disqualifying for a service with share links that must work months later, and Pro's **$0.09/GB egress** would apply to any asset served through Supabase Storage — reintroducing the exact cost curve decision 3 exists to delete. If you want Supabase, use it for auth + DB only and keep assets on R2; that is a defensible variant, at $25/mo minimum versus Neon's ~$3. |
| **Railway Postgres** | standard compute rates: ~$10/GB-RAM-mo + ~$20/vCPU-mo + $0.15/GB-mo volume; no scale-to-zero for a database container | The right answer *if* the API also lives on Railway — one platform, one bill, reference variables wire the `DATABASE_URL` automatically. Rejected only because decision 1 put the API on Modal. ~$10–15/month for a 1 GB instance that is idle 95% of the time. |
| **Fly Managed Postgres** | Basic (shared-2x, 1 GB) **$38/mo**; Starter (2 GB) $72; storage **$0.28/GB-month**. Version upgrades, security patching, alerting and migration tooling are listed as *still in progress* | $38/month minimum for the smallest instance, and the docs themselves list security patching as an in-progress feature. Not a foundation. |
| **AWS RDS** | not fetched — **[UNVERIFIED]**; a db.t4g.micro + gp3 storage + backups is conventionally ~$15–30/mo | Lowest lock-in (it is Postgres) but the highest operational surface per dollar: VPC, subnet groups, security groups, parameter groups, an IAM policy, and a bill that does not go to zero. Wrong shape for a solo builder. |
| **Self-hosted Postgres on Hetzner** | ~€5/mo | The cheapest and the most honest about what you are taking on: you own PITR, major-version upgrades, disk-full alarms and restore drills. A restore drill you have never run is not a backup. Revisit at 100× when the managed bill is four figures. |

### Schema sketch (what D5/D6/D7 need — not built)

```
users            id, email, created_at
sessions         token_hash, user_id, expires_at          -- magic link, HttpOnly cookie
clips            id, content_sha256 UNIQUE, uploaded_by, bytes, created_at   -- dedupe index
jobs             id, clip_id, state, stage_message, progress, error_json,
                 retry_count, created_at, updated_at      -- replaces {job_id}.job-status.json
lessons          id, job_id, owner_id, share_slug UNIQUE, title,
                 expires_at, deleted_at                   -- D6 retention, D7 deletion
assets           id, lesson_id FK ON DELETE CASCADE, kind, r2_key, bytes
```

`content_sha256 UNIQUE` on `clips` is the whole dedupe mechanism the `caching-retention`
branch needs: hash the upload, `INSERT … ON CONFLICT DO NOTHING`, and if the row already has
a completed job, skip the GPU entirely. **Note:** at the time of writing the local
`caching-retention` branch has **no commits ahead of `w4-jobservice`** and does not exist on
`origin`, so this is designed against the brief's description, not against code.

---

## 5. Decision 4 — job state and the queue

### What must not break

`apps/web/lib/jobStatus.ts::useJobStatus` polls `/api/jobs/{jobId}` every 2,000 ms, guards the
payload with `isJobStatus`, and stops polling on a terminal state. `ProcessingScreen.tsx`
renders `stage_message` history. `DESIGN.md` §7c promises *"You can close this"* with a
copyable link — the job must be resumable from `job_id` alone.

All of that already works and the contract is frozen. **Change nothing above the HTTP
boundary.**

### Recommendation

Keep HTTP polling. Do not introduce a queue, pub/sub, WebSockets or SSE. Move the *source of
truth* from `{job_id}.job-status.json` on the results Volume to a `jobs` row in Postgres, and
have `GET /jobs/{job_id}` serve the identical `job-status.schema.json` document assembled from
that row.

Why not a real queue: Modal's `.spawn()` **is** the queue. It is durable, it retries, it
survives a closed tab, and it already works. Adding Redis/SQS/Celery would add a component
whose only job is something the platform already does. The brief's own note calls the JSON
file provisional — the provisional part is the *file*, not the polling.

Why not push (SSE/WebSocket): polling at 0.5 Hz for 2–4 minutes is 60–120 requests per job. At
10,000 lessons/month that is ~1M requests — comfortably inside Workers' 10M included requests
and Modal's 200 req/s limit. Push would save money you are not spending and cost you
reconnection logic on a screen the learner is allowed to close. Revisit at 100× (§8).

### The one implementation risk, named

`run_clip` runs inside the pinned CV image and `export_clip_gltf` inside the pinned glTF image.
Writing to Postgres from them means adding `psycopg[binary]` to images that took seven bugs to
get green.

- **Preferred:** add `psycopg[binary]==<pin>` as a final `.pip_install()` layer. It ships
  self-contained wheels with a vendored libpq and touches neither CUDA, torch, onnxruntime nor
  numpy. Risk is low but non-zero given this repo's history (`rtmlib` silently clobbering
  `onnxruntime-gpu` is exactly this failure mode). Pin the version; do not let pip re-resolve.
- **Fallback if the image build goes red:** a tiny `@app.function(image=debian_slim)` called
  `record_status`, invoked with `.spawn()` (fire-and-forget) from the GPU functions. The pinned
  images stay untouched at the cost of ~8 extra container starts per job (≈$2/month at 10,000
  lessons). Take this immediately rather than debugging an image for a day.

Keep `write_status` writing the Volume JSON during the transition so a rollback is a one-line
revert in `api.py`. Delete the file write only after a week of clean production polling.

---

## 6. Decision 5 — frontend hosting (no Vercel)

### First: what does this Next.js app actually need? (Answered honestly before recommending)

I read every page on `w5-viewer` and `w7-marketing`:

- `app/page.tsx` (marketing), `app/upload/page.tsx`, `app/job/[jobId]/page.tsx`,
  `components/ProcessingScreen.tsx`, `components/DemoStage.tsx` — **all `"use client"`.** No
  server data, no server actions, no `fetch` on the server.
- `app/lesson/[lesson]/page.tsx` — an async server component that reads
  `public/fixtures/<lesson>.json` from disk with `generateStaticParams()`. Its own comment says
  it *"stands in for the job service's 'resolve this lesson' call (W4)"*. In production, lesson
  ids are unbounded job ids, so `generateStaticParams` cannot enumerate them.
- `next.config.mjs` is empty (`{ reactStrictMode: true }`). No `images`, no `output`, no
  rewrites yet.
- Client code fetches **same-origin** `/api/jobs` and `/api/jobs/{id}`.

So the real server-side requirements are exactly two:

1. **A same-origin `/api/*` path** that reaches the FastAPI service. Needed for cookies
   (D5 magic-link sessions want `HttpOnly; SameSite=Lax` on one origin) and to avoid CORS.
   Satisfiable with a `rewrites()` entry or a Worker route — no Node server required.
2. **Per-lesson OG/Twitter metadata**, server-rendered. `DESIGN.md` §7g calls the share clip
   *"the actual viral object"* and §A3 makes the shared-lesson link the growth loop. A link
   pasted into iMessage/WhatsApp/X is fetched by a crawler that does not run JavaScript. This
   is the only genuine SSR requirement in the product, and it is unavoidable.

**Nothing else.** No ISR, no `next/image` optimization, no middleware, no server actions, no
streaming RSC. That is a very cheap Next.js app to host, and it is worth saying plainly:
**this app does not need a Next.js-specific host.**

### Recommendation: Cloudflare Workers via `@opennextjs/cloudflare`

- Supports **all minor/patch versions of Next.js 16** and targets the **Node.js runtime**
  (not Edge), with App Router, SSR, SSG, dynamic routes and Route Handlers listed as supported
  ([opennext.js.org/cloudflare, retrieved 2026-09-20]). Only Node Middleware (Next 15.2+) is
  called out as not yet supported — this app uses no middleware.
- **Workers Paid: $5/month account minimum**, 10M requests and 30M CPU-ms included, then
  $0.30/million requests and $0.02/million CPU-ms. **Static asset requests are free and
  unlimited.** **No egress or bandwidth charges at all.**
  ([developers.cloudflare.com/workers/platform/pricing, retrieved 2026-09-20])
- Same account as R2 and DNS: `assets.<domain>` and the app share one origin family, one
  dashboard, one API token. The `/api/*` rewrite is a Worker route.
- Worker bundle size limit **10 MiB gzipped** on Paid. This app's server bundle is tiny
  (everything heavy — three.js, R3F — is client-side and served as static assets).

### The honest caveat, stated as the brief demands

`@opennextjs/cloudflare` is an **adapter between you and Next.js**. Next.js does not officially
support Cloudflare; the adapter tracks it. A Next.js minor release can break it, and when it
does you are waiting on someone else. That is a real dependency and it should not be
hand-waved.

The reason to accept it here is that **the blast radius is one day**. Because the app is
~95% client components with two trivial server requirements, `next start` in a container is a
drop-in fallback: `docker build`, deploy to Railway (~$5–10/month) or Fly (shared-cpu-1x
512 MB, ~$3.19/month), point DNS at it, done. Choose the cheaper CDN-native option *because*
the exit is cheap — not because it is guaranteed.

### Rejected

| Option | Why not |
|---|---|
| **Vercel** | Ruled out by the builder. (For the record the instinct is right: Vercel's Fast Data Transfer meters bandwidth, and this is a video + 3D-asset product.) |
| **Static export (`output: 'export'`) + R2** | The cheapest possible answer and it *almost* works: all the interactive pages are client components. It fails on requirement 2 — `generateMetadata` for an unbounded `[lesson]` route cannot run, so every shared link previews as a blank card. You could bolt on a Worker that injects OG tags for crawler user-agents, but that is clever rather than boring, and it is the kind of thing that silently rots. Rejected on §"prefer boring". |
| **Netlify** | Works fine technically. Rejected as the same category the builder excluded: bandwidth-metered, generous until it isn't. |
| **Self-hosted `next start` container** | The most boring option, zero adapter risk, and officially supported by the Next.js team. **This is the recommended fallback, and picking it first is also defensible.** Rejected as the default only because it costs more than $5/month, always runs, and you still need a CDN in front of the static assets — which means a Cloudflare account anyway. |
| **"Use a different framework"** | Worth asking, and the answer here is no. If the two server requirements were zero, a Vite SPA on R2 would be strictly simpler and I would say so. But per-lesson OG tags are a hard product requirement for the growth loop, and Next.js App Router is already written and working. Rewriting to escape a $5/month host would be the expensive choice. |

---

## 7. Decision 6 — secrets, environments, CI/CD, observability

The minimum credible setup. Everything here is free at this scale.

### Environments

Use **Modal Environments** — `modal environment create staging`, then `modal deploy --env=staging`.
Each Environment carries its own Secrets, and Volume/Function lookups resolve within the
Environment by default; a workspace supports up to 1,500 of them
([modal.com/docs/guide/environments, retrieved 2026-09-20]). Web Function URLs get a per-Environment
suffix, so staging and prod get distinct hostnames for free.

Two environments, no more: `staging` and `prod`. Mirror them:

| | staging | prod |
|---|---|---|
| Modal | Environment `staging` | Environment `prod` |
| Neon | a Neon **branch** off prod (branches are $1.50/branch-month beyond the included count) | primary |
| R2 | `stepwise-assets-staging` bucket | `stepwise-assets` bucket |
| Workers | `wrangler deploy --env staging` | `wrangler deploy` |

### Secrets

Modal Secrets already exist (`huggingface`). Add `stepwise-db` (`DATABASE_URL`, pooled), and
`stepwise-r2` (account id, access key, secret, bucket). The local `~/.stepwise-secrets/r2.env`
becomes the developer-machine copy only; Modal Secrets are the deployed source of truth.
Cloudflare side: `wrangler secret put`. No secret ever enters git, and `NEXT_PUBLIC_*` is
reserved for genuinely public values (the assets base URL).

The one rule worth writing down, because it is the failure mode that actually happens: **a
build-time environment variable that is absent produces a silently broken deploy, not an
error.** Add a startup assertion in `api.py` that every required env var is present and fails
loudly at import.

### CI/CD

GitHub Actions. The repo is **public from day one** (PRD §1), and Actions on standard runners
is free for public repositories with no practical minute limit. Three workflows:

1. `test.yml` on every push — `uv run pytest` (motion-contract python), `npm test`
   (contract TS + `apps/web` node:test), `npm run typecheck`. These suites already exist and
   already pass.
2. `deploy-staging.yml` on push to `main` — `modal deploy --env=staging`, `wrangler deploy
   --env staging`, then a smoke check against `/health` (which `api.py` already has).
3. `deploy-prod.yml` on a `v*` tag — the same, against prod. Tag-gated, manual, and therefore
   impossible to do by accident.

Do not build blue/green, canaries or migration automation yet. Schema migrations: keep plain
`.sql` files in `services/motion-api/migrations/` applied by hand at first. A migration tool
is worth adding at the second migration, not the first.

### Error tracking

**Sentry Developer (free): $0** — 5k errors/month, 5M spans, 50 replays, 30-day retention,
**1 uptime monitor and 1 cron monitor included** ([sentry.io/pricing, retrieved 2026-09-20]).
Wire it into three places: FastAPI (the `sentry-sdk` ASGI integration), the Modal GPU functions
(the `except` branches in `run_clip` already catch and re-raise — send there), and the browser.
Team is **$26/month** billed annually when 5k errors stops being enough.

The GPU worker matters more than the API here: `run_clip`'s failure path writes
`{"code": "pipeline_error", "retryable": True}` and raises. Without Sentry, the *reason* is in a
Modal log that **Starter retains for one day**. That is the most urgent gap in this whole
document — a user reporting yesterday's failure is already undebuggable.

### Uptime monitoring

**Better Stack free: $0** — 10 monitors, 10 heartbeats, 1 status page, 3-minute checks, Slack
and email alerts. Use three monitors (`/health`, the marketing root, one asset URL on the R2
custom domain) and one **heartbeat on the nightly retention sweep** so a cron that silently
stops running gets noticed.

### Logs — the one thing to actually pay for or work around

Modal Starter's **1-day log retention** is not enough to run a service. Options, cheapest
first: (a) ship structured logs from the API to Better Stack's free 3 GB/month log tier;
(b) write job outcomes to the `jobs` table you are building anyway, which gives permanent,
queryable history of every failure for free; (c) Modal Team at $250/month for 30-day
retention — not worth it yet. **Do (b), then (a).**

---

## 8. Decision 7 — the scale question, answered with arithmetic

### Assumptions, stated explicitly

| Assumption | Value | Basis |
|---|---|---|
| Mean clip length | 30 s | midpoint of the 60 s cap and the 19.7 s measured clip |
| Dancers per clip | 1.0 | PRD §5 allows up to 6; cost is linear per dancer |
| Warm GPU cost | **$0.00294 / clip-second** | measured $0.058 ÷ 19.7 s on L40S @ $1.95/hr |
| Reconstruction, 30 s clip | $0.088 | above × 30 |
| Cold start | ~35 s of L40S on 40% of jobs = **+$0.008** | `GATE-REPORT.md` records ~30 s load overhead |
| glTF export stage | ~45 s L40S incl. its own cold start = **$0.024** | separate image ⇒ separate container ⇒ separate cold start |
| Retries / failures | +10% | judgement, not measured |
| **GPU per lesson** | **$0.132** | (0.088 + 0.008 + 0.024) × 1.10 |
| Delivered payload per lesson view | **7.6 MB** | 5 MB video + 1.5 MB GLB + 1.1 MB JSON |
| Retained storage per lesson | **7.6 MB** (`.npz` deleted) or 65.9 MB (kept) | §3 |
| Views per lesson, creation month | 20 | the brief's "learners loop a lesson twenty times" |
| Cold fetches per lesson-month | **10** (50% absorbed by browser + CDN cache) | judgement; the sensitivity is modelled below |
| Retention window (D6) | **90 days** ⇒ steady-state stored lessons = 3× monthly rate | recommended in §9 |
| Plan floors | Workers Paid $5/mo; Modal Starter $0; Neon Launch no minimum | verified above |

### The table

| Line item | 100 lessons/mo | 1,000 lessons/mo | 10,000 lessons/mo |
|---|---|---|---|
| **GPU (Modal L40S)** | **$13.20** | **$132.00** | **$1,320.00** |
| API compute (Modal asgi_app) | $0.50 | $6.00 | $50.00 |
| Database (Neon Launch) | $3.00 | $12.00 | $39.00 |
| Object storage (R2) | $0.00 *(under 10 GB free)* | $0.20 | $3.42 |
| **Egress (R2)** | **$0.00** | **$0.00** | **$0.00** |
| R2 operations | $0.00 *(free tier)* | $0.00 *(free tier)* | $0.11 |
| Web hosting (Workers Paid) | $5.00 | $5.00 | $5.00 |
| Error tracking (Sentry) | $0.00 | $0.00 | $26.00 |
| Uptime (Better Stack) | $0.00 | $0.00 | $0.00 |
| CI (GitHub Actions, public repo) | $0.00 | $0.00 | $0.00 |
| Domain | $1.00 | $1.00 | $1.00 |
| **Total / month** | **≈ $23** | **≈ $156** | **≈ $1,444** |
| **GPU share** | **57%** | **85%** | **91%** |
| Egress volume | 7.6 GB | 76 GB | 760 GB |
| Stored bytes (steady state) | 2.3 GB | 22.8 GB | 228 GB |

### The dominant line item is GPU, at every scale

Not egress. The brief's crux — *"read-heavy, bandwidth-heavy; egress, not compute, is the cost
that grows"* — does not hold under these numbers, for two reasons: reconstruction is genuinely
expensive per unit (13 cents), and R2 charges nothing for bandwidth. **Bandwidth stops being a
cost curve the moment you pick decision 3.** That is the point of decision 3.

What egress *would* cost on the alternatives at 10,000 lessons/month (760 GB):

| Provider | Egress bill | Notes |
|---|---|---|
| R2 / Modal Volumes / Railway Buckets | **$0** | |
| CloudFront pay-as-you-go | $0 | 760 GB is inside the 1 TB always-free tier |
| CloudFront, at 10 TB/mo (≈2.6M views) | **~$765/mo** | 9 TB × $0.085 |
| S3 direct (no CDN) | ~$59/mo at 760 GB; ~$900/mo at 10 TB | $0.09/GB after 100 GB free |
| Supabase Storage (Pro) | ~$46/mo at 760 GB | 250 GB included, then $0.09/GB |
| Railway *service* egress (i.e. proxying bytes through your API) | **~$38/mo at 760 GB** | $0.05/GB — this is the byte-proxy tax made explicit |

So: at today's volume choosing R2 saves tens of dollars. At 10× it saves hundreds. The reason
to choose it is that **it is the only option where a surprise 100× week costs nothing extra**,
and a dance product's whole upside case is a surprise 100× week.

### Where the dedupe branch moves the needle

`caching-retention`'s content-hash index means a trending clip is reconstructed once and served
many times. Model 60% duplicate rate at 10,000 lessons/month:

- GPU: $1,320 → **$528**
- Everything else: unchanged
- Total: $1,444 → **$652**, GPU share 81%

Dedupe is by far the highest-leverage cost work available — a 40% hit rate cuts the total bill
by more than every other line item combined. It shifts the mix toward egress exactly as the
brief predicts, which is the second reason decision 3 is right. It does not make egress
*dominant*; it makes it visible.

### What breaks first

In order of when you hit it, not size:

1. **No database — blocks launch, today.** D5 (accounts), D6 (retention), D7 (deletion) are all
   unanswerable without one, and D7 is not optional once strangers can upload video of other
   people (D8, and the PRD's own note that both the Meta and NVIDIA licences restrict
   processing people without consent). This is the gate, not a scaling issue.
2. **Modal Starter's 1-day log retention — breaks the day you have your first user.** §7(b).
3. **`api.py`'s byte-proxying `/assets/{id}` — breaks video seeking, today.** No range requests.
   A product defect before it is ever a cost problem.
4. **Modal Starter's 10 GPU concurrency — breaks on a spike, somewhere past 10,000/month.**
   Steady state at 10,000 lessons/month is ~14 jobs/hour, ~3 concurrent at a 5× evening peak —
   comfortable. A 20× viral spike queues. The fix is Modal Team at **$250/month**, which is the
   single largest step function in this plan; note that it only becomes worth paying when the
   GPU bill is already four figures, so it never arrives as a surprise.
5. **Neon compute on the polling path — somewhere past 10,000/month.** 90 polls per job × 10,000
   jobs = 900k DB reads/month. Trivial. At 100× it is 90M and you would cache or push (§10).

---

## 9. What this unblocks: D5, D6, D7

These three are infrastructure-shaped and cannot be closed without decision 2. Recommendations,
so `docs/OPEN-DECISIONS.md` can be updated in one pass:

- **D5 — accounts: magic link, rolled by hand.** One `users` table, one `sessions` table, a
  signed token (`itsdangerous`), an `HttpOnly; Secure; SameSite=Lax` cookie, and **Resend** for
  delivery — free tier **3,000 emails/month, 100/day, one verified sending domain**, permanent,
  no card ([resend.com, retrieved 2026-09-20]). Watch the 100/day cap on launch day, and note
  the single-domain limit means staging and prod share a domain or you upgrade. This is roughly
  40 lines and has **no per-MAU meter**, which is the whole point: Clerk/WorkOS/Auth0 price per
  monthly active user, and an invite-only cohort that becomes public is exactly the shape that
  makes per-MAU pricing hurt later. If you would rather not own auth at all, the honest
  alternative is Supabase (§4) at $25/month.
- **D6 — retention: 90 days by default, stated on the landing page because the mockup already
  promises it.** `lessons.expires_at`, a nightly Modal cron (`@app.function(schedule=...)`) that
  deletes expired R2 objects and soft-deletes rows, and a Better Stack heartbeat on that cron.
  Separately and immediately: **delete the `.npz` 7 days after export** — 88% of stored bytes
  for an intermediate nobody reads.
- **D7 — deletion: yes, and the share link dies with it.** Set `deleted_at`, delete the R2
  objects, return **410 Gone** (not 404) on the share slug. **The part that is easy to get
  wrong: with a CDN in front, deleting the origin object does not delete the edge copy.** Issue
  a Cloudflare cache purge by URL as part of the delete transaction, or key assets so purging
  is a single prefix. A "deleted" video still served from an edge cache is a broken privacy
  promise, not a caching bug.

---

## 10. What I would do differently at 100× (100,000 lessons/month)

Written now so the foundation's limits are explicit rather than discovered.

- **GPU (~$13,200/month) stops being rentable per-second.** At that volume the 3× spread
  between Modal's L40S at $1.95/hr and RunPod-class 4090s at $0.34–1.10/hr (PRD §E1, still
  open) is ~$9,000/month — enough to justify a second GPU backend, a reserved-capacity
  commitment, or both. The current design survives this: `api.py` dispatches through one
  `Function.from_name(...).spawn()` call, so a second backend is one dispatch function, not a
  rewrite. **Keep it that way** — do not let GPU-provider specifics leak past that call.
- **Amortize the model load.** ~30 s of `SAM3DBodyEstimator.__init__` per container start is
  ~20% of a 30 s clip's cost. At 100× you batch several clips per container or hold warm
  workers with `min_containers`. Today that would be premature.
- **Job status leaves Postgres.** 90M polls/month is a real read load on a database sized for
  small rows. Move to push (SSE from the API, or a Cloudflare Durable Object per job) or cache
  status in Workers KV. Note that the *contract* does not change — `job-status.schema.json` is
  transport-agnostic, which is why freezing it early was right.
- **Egress at 100× is ~7.6 TB/month and still costs $0 on R2.** This is the decision that ages
  best and the reason it is worth making now while it is cheap to make.
- **Storage at 100× with 90-day retention is ~2.3 TB ⇒ ~$34/month.** Still noise. If it ever
  isn't, R2 Infrequent Access at $0.01/GB-month with a $0.01/GB retrieval fee is a 33% storage
  saving that only pays off for lessons older than the point where views go to near-zero —
  measure before switching.
- **The API leaves Modal.** At 100× you want an always-on fleet with real request metrics and a
  load balancer, not scale-to-zero. That is a Railway/Fly/Hetzner deployment of the same
  unchanged `api.py`.
- **What I would *not* change:** R2, Postgres, polling-over-HTTP, the frozen contract, or the
  two-image split. Those are the parts designed to survive.

---

## 11. Migration order from today's state

Each step is independently shippable and independently revertable. Nothing here requires
touching the pinned CV or glTF images except step 4, which has a named fallback.

| # | Step | Unblocks | Effort |
|---|---|---|---|
| 1 | **Deploy `api.py` as `@modal.asgi_app` in Environment `staging`.** No code change beyond the decorator. Confirm `/health`, upload → dispatch → poll → result end to end. | Everything. The service currently runs nowhere. | hours |
| 2 | **Provision Neon; write the schema in §4; add `stepwise-db` Modal Secret.** Nothing reads it yet. | D5/D6/D7 | hours |
| 3 | **Move job state to Postgres, API side only.** `GET /jobs/{id}` reads the row; `POST /clips` inserts it. The worker still writes the Volume JSON; the API reconciles. Frontend untouched. | removes 900k/month Volume control-plane reads | ~½ day |
| 4 | **Worker writes status directly to Postgres.** Add pinned `psycopg[binary]` to both images, or the `record_status` sidecar function if the build goes red. Delete the Volume JSON write after a week clean. | one source of truth | ~½ day |
| 5 | **R2 bucket + custom domain + Workers Paid ($5/mo).** Write video/GLB/`MotionResult` to R2 at job completion; `GET /assets/{id}` becomes a 302. Set `Cache-Control: public, max-age=31536000, immutable`. | fixes video seeking; deletes the egress curve | ~1 day |
| 6 | **Presigned PUT for uploads.** Browser uploads straight to R2; `POST /clips` takes a key, not a file. The API stops handling video bytes entirely. | removes the tempfile → Volume double hop | hours |
| 7 | **Delete the `.npz` 7 days post-export; add the nightly retention cron + heartbeat.** | 88% of stored bytes; D6 | hours |
| 8 | **Deploy `apps/web` to Cloudflare Workers via OpenNext**, with `/api/*` rewritten to the Modal ASGI URL. Add `generateMetadata` to the lesson route for OG tags. | the share loop | ~1 day |
| 9 | **Sentry in all three places; Better Stack monitors; the three GitHub Actions workflows.** | debuggability | ~½ day |
| 10 | **Magic-link auth (D5).** Last, because it is the only step that is product-visible and the only one that can wait behind an invite code. | accounts, ownership, D7 | ~1 day |
| 11 | **Dedupe index on `clips.content_sha256`** (the `caching-retention` work, once that branch exists). | the single biggest cost lever | — |

### Must be decided before public launch

- D7 deletion, end to end **including CDN purge** — a privacy promise you cannot keep is worse
  than one you never made.
- D6 retention window, stated on the landing page, matching what the cron actually does.
- D5 accounts — the invite-only cohort needs identity for D7 to mean anything.
- Read Cloudflare's canonical Service-Specific Terms on CDN video, and be on Workers Paid.
- Log retention: job outcomes persisted to Postgres (Modal's 1 day is not a record).
- DMCA/abuse contact + takedown path, since `evaluation/clips.yaml` records rights as
  `untested` and public share links change the exposure.

### Can wait

- Modal Team plan ($250/mo) — only when GPU concurrency actually queues.
- Push-based job status — polling is fine to ~100×.
- A migration tool — add it at the second migration.
- Multi-region anything.
- RunPod / second GPU backend (PRD E1) — the dispatch seam already exists; decide with real
  volume.
- Infrastructure-as-code. Two `modal deploy` commands and a `wrangler deploy` are not worth a
  Terraform state file yet.

---

## 12. What I could not verify

Listed plainly, per ground rule 1.

1. **Modal's `scaledown_window` default.** The official scaling page documents the parameter
   but does not print a default; secondary sources say 60 s (and separately note that a
   deprecated `container_idle_timeout` had 300 s). Confirm before relying on idle-tail cost
   estimates.
2. **Whether Modal bills a `min_containers` warm container.** Not stated on any page I reached.
   Assume yes (it is a running container) and do not enable it speculatively.
3. **S3 Standard storage $/GB-month.** AWS's own pricing table did not render; $0.023/GB-month
   is taken from Railway's published comparison table, which is a competitor's page. The
   $0.09/GB egress and 100 GB free allowance *are* from AWS's page.
4. **AWS RDS pricing.** Not fetched at all. The ~$15–30/month figure is conventional knowledge,
   not a citation.
5. **Hetzner's current prices.** Every Hetzner page I reached had the numbers stripped.
   Secondary sources give CPX11 from €4.99/mo and €1/TB overage, but Hetzner ran a price
   adjustment on **2026-06-15** and the CX line appears to have been superseded (CX22 → CX23),
   with CX/CAX shown as unavailable as of September 2026. Treat all Hetzner figures as
   indicative.
6. **Whether Cloudflare's current CDN terms explicitly permit R2-origin video.** The
   2026-06-02 Service-Specific Terms name "Developer Platform, Images, Stream" as the paid
   services required to serve video; the rendering I retrieved did not name R2, and the page
   text had words dropped. Cloudflare's 2023 blog says R2-hosted content qualifies. There is a
   documented history of false-positive enforcement against R2-backed video. **This is the
   single most important thing on this list to check yourself.** I am not a lawyer.
7. **The workload sizes.** `MotionResult` ~1.1 MB, GLB ~1.5 MB and `.npz` 58.3 MB are taken
   from the brief as measured. I could not reproduce them from the branch: the repo's
   `MotionResult` fixtures are hand-built (1.9 MB raw, 31 KB gzipped — a compression ratio real
   float data will not achieve), and the only GLB size recorded in `GATE-REPORT.md` is the
   589 KB single-frame neutral-pose smoke test. The 5 MB 60-second video is my extrapolation
   from a 19.7 s 576×1024 clip. **Re-measure all four on one real end-to-end job before
   trusting the cost table's egress and storage rows** — the GPU row, which dominates, rests on
   a genuinely measured number and is not affected.
8. **The `caching-retention` branch.** It exists locally with **zero commits ahead of
   `w4-jobservice`** and is not on `origin`. The dedupe design in §4 and the modelling in §8
   are written against the brief's description of it, not against code.
9. **Neon's Launch/Scale CU-hour split.** The pricing page's compute row rendered garbled; the
   plans doc corroborates $0.106 (Launch) / $0.222 (Scale). Re-check before budgeting.
10. **Egress cache-hit rate.** The "10 cold fetches per lesson-month" assumption is judgement,
    not data. It is the single largest lever on the egress rows — but since egress is $0 under
    the recommendation, getting it wrong costs nothing. That asymmetry is itself an argument
    for the recommendation.

---

## Sources

All retrieved **2026-09-20** unless noted.

- Modal pricing — <https://modal.com/pricing>
- Modal web endpoints — <https://modal.com/docs/guide/webhooks>
- Modal scaling — <https://modal.com/docs/guide/scale>
- Modal environments — <https://modal.com/docs/guide/environments>
- Cloudflare R2 pricing — <https://developers.cloudflare.com/r2/pricing/>
- Cloudflare R2 public buckets — <https://developers.cloudflare.com/r2/buckets/public-buckets/>
- Cloudflare Workers pricing — <https://developers.cloudflare.com/workers/platform/pricing/>
- Cloudflare Service-Specific Terms, Application Services (last updated 2026-06-02) — <https://www.cloudflare.com/service-specific-terms-application-services/>
- Cloudflare, "Goodbye, Section 2.8" (2023-05-16) — <https://blog.cloudflare.com/updated-tos>
- OpenNext for Cloudflare — <https://opennext.js.org/cloudflare>
- Neon pricing — <https://neon.com/pricing> and <https://neon.com/docs/introduction/plans>
- Supabase pricing — <https://supabase.com/pricing>
- Railway pricing — <https://railway.com/pricing>
- Railway Storage Buckets — <https://docs.railway.com/storage-buckets>
- Fly.io pricing — <https://fly.io/docs/about/pricing/>
- Fly.io Managed Postgres — <https://fly.io/docs/mpg/>
- Backblaze B2 pricing — <https://www.backblaze.com/cloud-storage/pricing>
- AWS S3 pricing — <https://aws.amazon.com/s3/pricing/>
- AWS CloudFront pricing (flat-rate) — <https://aws.amazon.com/cloudfront/pricing/>
- AWS CloudFront pricing (pay-as-you-go) — <https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/>
- Sentry pricing — <https://sentry.io/pricing/>
- Resend pricing — <https://resend.com/pricing>
- Better Stack uptime — <https://betterstack.com/uptime>
- GitHub Actions billing — <https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions>
- Hetzner Cloud — <https://www.hetzner.com/cloud/regular-performance/> (prices did not render; see §12)
