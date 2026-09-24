# Deployment

**Written 2026-09-21, branch `deployment`.** What is live, what is one command
away, and what to do when it breaks. Assume you are reading this at 2am with
something on fire; the runbook is §7 and it is deliberately near the end so the
table of contents gets you there in one scroll.

The architecture is not decided here. It was decided in
`docs/research/infrastructure.md` (branch `research-infrastructure`), which has
the prices, the rejected alternatives and the reasoning. This file only records
execution.

---

## 1. What is live, right now

| | Status | Where |
|---|---|---|
| **HTTP API** | **LIVE** | `https://sreshta-talluri--stepwise-motion-web.modal.run` |
| Dispatch rate limit | **LIVE** — per learner IP (forwarded by the Worker), retries charged and capped at 2, link downloads pre-checked | 5/h · 20/day per IP, 200/day global, `STEPWISE_LIMIT_*` |
| GPU pipeline | live (unchanged) | Modal app `stepwise-motion`, workspace `sreshta-talluri`, environment `main` |
| Asset delivery | **BROKEN since ≤2026-09-23 — R2 rejects the credentials** (`Unauthorized` on Put/Head/List, both the `stepwise-r2` Secret and `~/.stepwise-secrets/r2.env`). Serving falls back to the Volume proxy: lessons open, video seeking does not. `/health` still says `r2` because it checks env names, not access. Fix: new R2 API token → `modal secret create stepwise-r2 --force …` | Cloudflare R2 bucket, presigned URLs (no custom domain yet) |
| Retention sweeper | live, daily | `sweep_expired`, `modal.Period(days=1)` |
| Job state | **LIVE on Postgres** (Neon), Volume read-through (migration step 3) | `stepwise-db` Secret, `STEPWISE_JOB_BACKEND=postgres` |
| CI | live | `.github/workflows/test.yml`, push + PR |
| Database | **LIVE** — Neon, `001_init` applied | §5.1 |
| Frontend hosting | **LIVE** — Cloudflare Worker (OpenNext), no custom domain yet | `https://stepwise.sreshta-talluri.workers.dev`; `/api/*` is `app/api/[...path]/route.ts` → Modal |
| Origin lock | **LIVE** — the Modal API answers only the Worker (404 otherwise; `/health` open) | Modal Secret `stepwise-origin` = Worker secret `STEPWISE_ORIGIN_KEY`, value in `~/.stepwise-secrets/origin.env`. Calling the API direct (e2e_check.py): export that file first |
| Error tracking | **backend LIVE** (`stepwise-sentry` Secret exists, deployed); browser goes live with the frontend deploy | §5.3 |

One app, one `modal deploy`, one set of credentials. `api.py` was already a
Modal client — it constructs `modal.Volume.from_name(...)` at import and
dispatches with `Function.from_name(APP_NAME, "run_clip").spawn()` — so putting
it behind `@modal.asgi_app()` collapsed two credential sets into one. The
coupling is exactly one decorator deep: `uvicorn api:app` still runs the same
file on Railway, Fly or a box, which is the only reason picking the
tightly-coupled option was defensible.

### Measured against the live URL

Real requests, 2026-09-21, not estimates. Reproduce with
`python3 services/motion-api/e2e_check.py <url> <clip.mp4>` — it costs one real
GPU reconstruction, so it is a deliberate act, not a health check.

```
GET  /health              200   5.14 s cold, 0.39 s warm
POST /clips               200   7.80 s   (946 KB clip, 8 s of video)
GET  /jobs/{id}           38 polls at 2 s, 111.4 s to `succeeded`
                          every single poll validated against job-status.schema.json
GET  /jobs/{id}/result    200   6.45 s   2,889,578 bytes, schema-valid, 1 person
GET  /assets/video:…      302 -> R2
     Range: bytes=0-1023  206   Content-Range: bytes 0-1023/946547
GET  /assets/…_track1.glb 302 -> R2
     Range: bytes=0-1023  206   Content-Range: bytes 0-1023/1408092
                          Cache-Control: public, max-age=31536000, immutable
```

And the takedown path, against that same live lesson (`POST
/lessons/{clip_id}/removal`) — because a delete path that knows about one of two
storage systems is not a storage leak, it is a privacy leak:

```
removed: 9 Volume paths
       + r2:video/…​.mp4
       + r2:motion-result/…​.json.gz
       + r2:glb/…_track1.glb
already_absent: []

GET /jobs/{id}      410      GET /assets/video:…  410      GET /assets/…glb  410
R2 objects still holding that lesson: none
```

**The 206 is the point.** `api.py::_volume_read_bytes` did
`volume.read_file_into_fileobj(path, buf)` then `buf.getvalue()` — the whole
object into memory, returned as one `Response`. A `<video>` asking for
`Range: bytes=…` got a 200 with the entire body, so scrubbing (DESIGN.md §7c's
core interaction) downloaded the whole clip before the first seek resolved.
That was a product defect, not a cost problem. R2 fixes it because R2 speaks S3
and S3 GETs honour `Range`.

---

## 2. Deploying

```sh
cd services/motion-api
modal deploy modal_app.py          # API + GPU functions + sweeper, all one app
```

That is the whole deploy. It takes ~20 s when no image layer changed.

**Before you believe a deploy took effect, read §7.1.** A warm container
survives `modal deploy` when only a mounted local directory changed, and W4
lost time to a container serving pre-fix code across two deploys.

### Smoke check

```sh
curl -s https://sreshta-talluri--stepwise-motion-web.modal.run/health | jq
```

```json
{
  "ok": true,
  "assets": "r2",
  "assets_missing_env": [],
  "assets_url_mode": "presigned",
  "jobs": { "backend": "volume", "database_url_set": false },
  "dedupe": "perceptual"
}
```

Read it as a configuration report, not a liveness ping:

| Field | Good | Bad, and what it means |
|---|---|---|
| `assets` | `r2` | `volume-proxy` — **video seeking does not work.** The R2 Secret is missing or wrong; `assets_missing_env` names which variable. |
| `assets_url_mode` | `presigned` today | `custom-domain` once §5.2 is done. Presigned means no edge caching, and URLs expire in 6 h. |
| `jobs.backend` | `volume` today | `postgres` after §5.1 cutover. |
| `dedupe` | `perceptual` | `sha256-only` — ffmpeg is missing from the image, and every re-encode of an already-reconstructed clip now costs a fresh $0.08 GPU run. Never a *wrong* match, just fewer matches. |

`/health` reports rather than asserts, on purpose. infrastructure.md §7 names
the failure mode — *"a build-time environment variable that is absent produces a
silently broken deploy, not an error"* — and argued for a hard assertion at
import. A hard assertion is wrong here: "no R2" and "no database" are both
deliberate, supported configurations during this migration, and failing to boot
on them would mean the service cannot be deployed until every credential exists,
which is exactly what this branch was built to avoid.

---

## 3. Secrets — what each thing needs

Nothing secret is in the repo. `~/.stepwise-secrets/r2.env` is a
developer-machine copy only; the Modal Secrets are the deployed source of truth.

| Secret | Keys | Used by | Exists? |
|---|---|---|---|
| `huggingface` | `HF_TOKEN` | `download_weights` | **yes** |
| `stepwise-r2` | `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, *(later)* `R2_PUBLIC_BASE_URL` | `web`, `export_clip_gltf`, `sweep_expired`, `verify_r2_access` | **yes** — created 2026-03, **verified working 2026-09-21** |
| `stepwise-db` | `DATABASE_URL` (pooled), `STEPWISE_JOB_BACKEND=postgres` | `web` | **no** — blocked on Neon |

### Verifying `stepwise-r2` rather than trusting it

The Secret predated everything that now uses it, so it was checked against the
live bucket from inside Modal, not assumed:

```sh
modal run modal_app.py::verify_r2_access
# [verify_r2_access] {'ok': True, 'status': 206,
#                     'content_range': 'bytes 100-199/16384', 'bucket_env_set': True}
```

It writes one 16 KB object under `diagnostic/`, range-reads it, compares the
bytes, and deletes it. Two Class A operations. It never prints a credential.
The laptop-side equivalent is `python3 services/motion-api/verify_r2.py`.

### Creating the ones that do not exist

```sh
# Once Neon exists. Use the POOLED connection string -- this API scales to zero
# and back up, so the far end has to tolerate connections appearing in bursts.
modal secret create stepwise-db \
  DATABASE_URL='postgresql://…@…-pooler.….neon.tech/stepwise?sslmode=require' \
  STEPWISE_JOB_BACKEND=postgres

# Once a domain and Workers Paid exist, to switch R2 off presigned URLs.
# --force replaces the whole Secret, so all five keys must be given together.
modal secret create stepwise-r2 --force \
  R2_ENDPOINT_URL=…  R2_ACCESS_KEY_ID=…  R2_SECRET_ACCESS_KEY=… \
  R2_BUCKET_NAME=…   R2_PUBLIC_BASE_URL=https://assets.<domain>
```

`modal_app.py::optional_secret()` hydrates each Secret at load time and
continues without it if it is absent. This matters more than it looks:
`modal.Secret.from_name` is **lazy**, so a `try/except` around it catches
nothing and one missing Secret fails the entire `modal deploy` — including every
function that never referenced it. That is what "the API cannot be deployed
until Neon exists" would have looked like.

### Environments

`staging` exists (`modal environment create staging`); `main` is production.

**Nothing is deployed to `staging` yet, deliberately.** A staging deploy is not
free the way it looks: `modal.Volume.from_name(..., create_if_missing=True)`
resolves per-environment, so `stepwise-weights` would be created *empty* in
`staging` and `download_weights` would have to pull ~8 GB of gated SAM-3D-Body
checkpoints again. Do it when there is something to stage, and budget the
weights download:

```sh
modal secret create stepwise-r2 --env=staging …     # point at a staging bucket
STEPWISE_GPU= modal run --env=staging modal_app.py::download_weights
modal deploy --env=staging modal_app.py             # URL gets a -staging suffix
```

---

## 4. Storage layout

| Artifact | Lives on | Why |
|---|---|---|
| Source video | **R2** `video/{clip_id}.mp4` + uploads Volume | R2 for delivery (range requests); the Volume copy stays because `run_clip` reads its input from there. Removing that double-hop is migration step 6 (presigned browser uploads). |
| GLB, per dancer | **R2** `glb/{clip_id}_track{n}.glb` | Delivered to the browser. |
| MotionResult | **R2** `motion-result/{clip_id}.json.gz` + results Volume | Delivered; also read back by `GET /jobs/{id}/result`, which must parse and contract-validate it, so it is the one delivered artifact that cannot just be a 302. |
| `.npz` | results Volume only | Pipeline-internal, 58 MB, never touched by a browser. Deleted by the sweeper once the MotionResult is materialised. |
| Model weights | weights Volume | Never leaves the cluster. |
| Job status | results Volume JSON (Postgres ready) | §5.1. |

Writers: `api.py::_publish_video` at upload (the bytes are already on that
machine — publishing later would mean reading a 5 MB object back out of a Volume
for nothing) and `modal_app.py::_publish_to_r2` at the end of
`export_clip_gltf` (the first instant every delivered byte exists).

Both are **best-effort**: an R2 failure logs loudly and the job still succeeds,
because a lesson served through the old byte proxy is degraded, not lost. The
cost of that degradation is exactly one thing — no video scrubbing — and
`/health` reports it.

Deleter: `retention.delete_clip` → `_delete_r2_objects`, one function called by
both the takedown endpoint and the sweeper. A deletion path that knows about one
of two storage systems is not a storage leak, it is a privacy leak: the video is
what R2 is holding and the video is what the dancer asked to have gone.

---

## 5. Blocked on a credential — and the exact command for each

Everything here is code-complete and tested against a local substitute. None of
it needs code to finish; all of it needs a credential.

### 5.1 Neon Postgres → job state, and D5/D6/D7

**Done** — the steps below were run; `/health` reports `"backend":"postgres","postgres":"ok"`. Kept as the record, and as the rebuild procedure.

**Bug found after cutover, fixed in `4669792`:** `record_dispatch` inserts the row as `queued` and the worker writes only the Volume, so serving the row whenever it existed meant the read-through never ran and every job read `queued` forever. `read_status` now serves a terminal row as-is and otherwise lets the Volume document win.

**Already done:** `services/motion-api/migrations/001_init.sql` covers `users`,
`creator_tokens`, `sessions`, `clips` (with the `content_sha256 UNIQUE` dedupe
index and the perceptual `fingerprint jsonb`), `jobs`, `lessons` (with
`last_access_at` for retention and `removed_at`/`removed_reason` for
tombstones), `assets` and `events`. Applied and re-applied against a plain
Postgres 16 container; `pg_dump --schema-only` exits clean at 11,322 bytes with
**zero Neon references**, which is the property decision 2 rests on.
`test_schema.py` (12 tests) runs against that container in CI.

**To finish:**

```sh
# 1. create the Neon project, copy the POOLED connection string
# 2. apply the schema
DATABASE_URL='postgresql://…-pooler.…neon.tech/stepwise?sslmode=require' \
  python3 services/motion-api/migrate.py
#    -> "apply 001_init"  then  "tables: assets, clips, creator_tokens, …"
#
#    If the Neon endpoint is not reachable from your laptop, migrations/ is
#    mounted into the API image for exactly this: `modal shell` into the `web`
#    function and run `python3 /app/services/motion-api/migrate.py` there.

# 3. hand it to Modal and flip the backend
modal secret create stepwise-db \
  DATABASE_URL='…'  STEPWISE_JOB_BACKEND=postgres
modal deploy modal_app.py

# 4. confirm
curl -s <api>/health | jq .jobs
#    -> {"backend":"postgres","database_url_set":true,
#        "postgres":"ok","migrations_applied":1}
```

**Rollback:** `modal secret create stepwise-db --force DATABASE_URL='…'`
(i.e. drop `STEPWISE_JOB_BACKEND`) and redeploy. Nothing is lost, because in
postgres mode the GPU worker is *still* writing the Volume JSON and the API
reads through to it on a row miss — that is migration step 3, and it is what
makes a job already in flight at cutover keep reporting correctly.

**Not done, on purpose:** migration step 4, the worker writing Postgres directly
and the Volume write being deleted. It means adding `psycopg` to the two pinned
GPU images, which took seven environment bugs to get green (GATE-REPORT.md G3),
in exchange for removing a read from a path that is already correct.
infrastructure.md §5 says to do it after a week of clean production polling;
there has not yet been a day. When you do: add
`.pip_install("psycopg[binary]")` as the **last** layer of `cv_image` and
`gltf_image`, and replace `run_clip::write_status`'s Volume write with a call
into `jobstore._pg_write`. Keep the Volume write for a week after that; deleting
it is the irreversible half.

### 5.2 Cloudflare Workers Paid + domain → custom asset domain, and the frontend

**Blocked on:** a Cloudflare account id, an API token, a domain, Workers Paid
($5/mo — **this costs money; it has not been bought**).

R2 assets are served today through **presigned GET URLs**, valid 6 hours. They
give real 206 range responses, which is the thing that mattered, and they miss
the edge cache, which is the thing that does not matter yet.

**To finish:**

```sh
# 1. bind a custom domain to the bucket in the Cloudflare dashboard
#    (R2 -> bucket -> Settings -> Public access -> Custom domain), e.g.
#    assets.<domain>. Enable Smart Tiered Cache.
# 2. tell the API to stop signing
modal secret create stepwise-r2 --force \
  R2_ENDPOINT_URL=… R2_ACCESS_KEY_ID=… R2_SECRET_ACCESS_KEY=… \
  R2_BUCKET_NAME=… R2_PUBLIC_BASE_URL=https://assets.<domain>
modal deploy modal_app.py
curl -s <api>/health | jq .assets_url_mode      # -> "custom-domain"
```

No code changes. `storage.url_for()` already branches on
`R2_PUBLIC_BASE_URL`, and rollback is removing that one key.

**Two things that become true the moment there is a CDN, and are not handled:**

1. **Deleting the origin object does not delete the edge copy.** A removed
   video still served from an edge cache is a broken privacy promise, not a
   caching bug. `retention._delete_r2_objects` must also issue a Cloudflare
   cache purge for the same keys, which needs an API token that does not exist.
   The TODO is written at the function, not only here.
2. **Cloudflare's CDN content restriction.** The Service-Specific Terms
   (Application Services, last updated 2026-06-02) reserve the right to limit
   serving video via the CDN without Paid Services. infrastructure.md §3's
   mitigation is to be an unambiguous paid Developer Platform customer. **Do not
   run this on the free plan to save $5.** Read the canonical terms before
   public launch; the escape hatch, if it ever becomes real, is Backblaze B2 +
   bunny.net, reachable with `rclone sync` precisely because nothing here uses a
   Cloudflare-specific SDK.

For `apps/web` itself (migration step 8) nothing has been built. The app builds
and typechecks clean and CI proves it on every push; the OpenNext deploy, the
`/api/*` rewrite to the Modal URL, and `generateMetadata` on the lesson route
are all still to do and all need the Cloudflare account first.

### 5.3 Sentry

**Backend switched on 2026-09-23.** The first switch-on deploy took the API down for ~15 minutes: the `STEPWISE_GIT_SHA` `Secret.from_dict` was attached only when git was readable, so the deploy declared one more dependency than the container's re-import, and every function died at startup with *"Function has 6 dependencies but container got 7 object ids"*. Fixed in `c620bf3` (always attached). **Any per-function object in `modal_app.py` must be declared identically locally and in the container.** Modal Starter retains logs for **one
day**, so without this a user reporting yesterday's failure is already
undebuggable.

What reports, all through `services/motion-api/observability.py` (backend) and
`apps/web/instrumentation-client.ts` (browser):

| Where | What | Project |
|---|---|---|
| `run_clip` | `pipeline_error` and `export_error` as errors, a failed beat stage as a warning, each tagged `clip_id` / `job_id` / `stage` / `retry_count` | `stepwise-backend` |
| `sweep_expired` | any crash (a dead sweeper is a broken retention promise) | `stepwise-backend` |
| `web` (FastAPI) | unhandled 500s via the ASGI integration; 10% of requests traced (`SENTRY_TRACES_SAMPLE_RATE`) | `stepwise-backend` |
| browser | uncaught errors, plus render errors caught by `app/global-error.tsx`; no tracing, no replay | `stepwise-web` |

**Nothing identifying leaves.** Every event, breadcrumb and log is scrubbed as a
whole before send: URLs with a scheme, schemeless `tiktok.com/…` links,
yt-dlp's `[youtube] <id>:` shape, `tiktok:<id>` source keys, emails and
`@handles`. Presigned R2 URLs are caught by the same rule, and they matter as
much as source links, because each one carries a live signature. Local variables
are not captured and request bodies are never sent. The browser keeps its own
page URL (path only, query dropped). `test_observability.py` asserts on the
serialized envelope from a real FastAPI app, and it goes red if the scrubber is
unhooked.

**`release` is the deployed commit.** It is read from git on the deploying
machine at `modal deploy` / `cf:build` time, with `-dirty` appended for an
uncommitted tree. It rides in as a per-function `modal.Secret.from_dict`, not
an image layer, so no rebuild per commit. The same field exposes §7.1's
warm-container trap: if an error after a deploy carries the *previous* sha, it
came from a container that outlived the deploy. The Sentry GitHub integration is
deliberately **not** connected, because Sentry would resolve commits against
the default branch, and that is the abandoned v1.

To switch on, with `SENTRY_DSN_BACKEND` and `SENTRY_DSN_WEB` in
`~/.stepwise-secrets/sentry.env`. Modal does not mind that the Secret also holds
the web DSN:

```sh
modal secret create stepwise-sentry --from-dotenv ~/.stepwise-secrets/sentry.env
cd services/motion-api && modal deploy modal_app.py
modal container list   # then `modal container stop` any warm web container (§7.1)

# Browser: the DSN is inlined at build time, so it must be in the build's env.
cd apps/web && set -a && . ~/.stepwise-secrets/sentry.env && set +a && npm run cf:deploy
```

The backend also accepts a plain `SENTRY_DSN` if the file uses that name.

---

## 6. CI

`.github/workflows/test.yml`, on push and pull request. Public repo, so Actions
minutes are free and nothing is pruned by changed paths — the one thing this
exists to catch is the cross-package breakage that path filters hide
(INTEGRATION.md §9 is a list of things that only broke once the pieces met).

Nine jobs: four Python suites, one Postgres job (schema + job-state backend,
against `postgres:16` as a service container), three Node packages, and
`apps/web` build + typecheck.

**Test gate only. No deploy-on-merge.** infrastructure.md §7 sketches
`deploy-staging.yml` and `deploy-prod.yml`; neither is built, because neither
should exist before a staging environment does. A workflow that deploys
somewhere that does not exist is not automation, it is a broken build nobody can
fix.

Three real setup gaps the first run found, all now fixed, recorded because they
will bite again in any new environment:

* `packages/motion-contract/python` needs **pydantic** — `__init__.py` imports
  the generated models even though the tests only use `validate`.
* The `vendor/fast-sam-3d-body/tools` suites must run **from inside `tools/`**
  and need **onnxruntime + rtmlib**; those modules import each other by bare
  name, so the directory has to be on `sys.path`.
* `apps/web` needs **`npm run assets`** before both `npm test` and `npm run
  build`. The fixtures are generated and not committed, and
  `app/lesson/[lesson]` is a server component that reads one off disk at build
  time — so a missing fixture is a prerender failure, not a missing page.

What CI deliberately does not run: anything needing a GPU, `e2e_check.py` (it
costs a real reconstruction), and `test_fingerprint.py`'s measurement mode
(`STEPWISE_FP_CLIPS`, which wants four real eval clips out of a Modal Volume).

---

## 7. Runbook

### 7.1 "I deployed the fix and it is still broken"

**A warm Modal container survives `modal deploy` when only a mounted local
directory changed.** This is the single most expensive trap in this repo — W4
lost time to a container serving pre-fix code across two deploys — and it is
likely now, because `api.py`, `storage.py` and `jobstore.py` are all *mounts*
on `api_image`, not image layers.

```sh
modal container list
modal container stop <container-id>
```

Then re-request. If the behaviour changes, that was it.

### 7.2 `/health` says `"assets": "volume-proxy"`

Video seeking is broken for every lesson served while this is true. Read
`assets_missing_env` — it names the variable. Then:

```sh
modal secret list                       # is stepwise-r2 there at all?
modal run modal_app.py::verify_r2_access   # do the keys actually work?
```

If `verify_r2_access` returns `{"ok": false, "missing": [...]}` the Secret is
incomplete. If it raises a `ClientError`, the keys are wrong or the bucket was
renamed. Recreate with `modal secret create stepwise-r2 --force` and **all**
keys — `--force` replaces the whole Secret, it does not merge.

### 7.3 A job is stuck in `processing` and never finishes

`run_clip` writes its status to a **Volume**, and Modal Volumes are commit-based
and eventually consistent — `run_clip` already calls `uploads.reload()` for a
real race, with the comment *"this is a Volume, not a queue — no delivery
guarantee beyond eventually consistent."* So a status that looks stale may be
stale rather than stuck.

1. `modal app logs stepwise-motion` — is the container alive? (One day of
   retention. If it is older than that, you cannot answer this; see §5.3.)
2. If the worker died, the status document simply stops updating; there is no
   watchdog. `POST /jobs/{job_id}/retry` re-spawns at the same `job_id` and
   increments `retry_count` — but only for a document whose `error.retryable`
   is true, so a genuinely wedged job needs the worker's last state fixed first.

**Build nothing new on read-after-write over Volume semantics.** That is the
entire reason Postgres is being added (§5.1), and it is why `jobs` has real
CHECK constraints rather than a convention.

### 7.4 The retention sweeper deleted something it should not have

`sweep_expired` defaults to **`dry_run=False`** and is invoked by a daily
schedule. Always dry-run first:

```sh
modal run modal_app.py::sweep_expired --dry-run
# sweep: 2 superseded npz, 0 lessons past 180d since last open, 10 kept (dry_run=True)
```

That is the real output from 2026-09-21: the schedule is registered, the dry run
works, and it currently has nothing destructive to do. Deletions are **not
recoverable** — there is no soft-delete of bytes, only a tombstone of the
record.

The retention clock is `last_access_at`, not `created_at`: 180 days since the
lesson was last *opened* (`retention.TTL_DAYS`, OPEN-DECISIONS D6). `api.py`
throttles that write to one per clip per day per container, so a lesson opened
today cannot age out.

### 7.5 A removal returned 500

It should not any more, and the fix must survive any refactor of
`retention.delete_clip`. **`Volume.commit()` raises outside a container** —
"commit() can only be called on a mounted volume inside a container" — so
calling it from the API process returns a 500 to someone *after* their lesson
has in fact been deleted. `delete_clip` therefore calls no `commit()` at all:
`remove_file` and `batch_upload` are client API calls and the bytes are already
gone server-side. `test_retention.py`'s `FakeVolume.commit()` raises on purpose
to keep that true.

### 7.6 Cold starts

First request after idle boots a container: measured **5.14 s** cold versus
0.39 s warm on `/health`. Invisible on upload, invisible after the first
two-second job poll. `min_containers=1` would remove it and pin roughly
$45/month of always-on container — do not pay that speculatively, only if a
real user complains.

### 7.7 Rolling back

| Change | Roll back by |
|---|---|
| Job state → Postgres | drop `STEPWISE_JOB_BACKEND` from `stepwise-db`, redeploy. The Volume JSON was never stopped. |
| Assets → R2 custom domain | drop `R2_PUBLIC_BASE_URL`, redeploy. Back to presigned. |
| Assets → R2 entirely | delete the `stepwise-r2` Secret, redeploy. Back to the Volume byte proxy: works, no range requests. |
| The whole API deploy | `git revert` and `modal deploy`. Then **§7.1** — stop the warm container. |

Every one is a Secret change plus a redeploy. None is a code change. That was
the design constraint, not a coincidence.

---

## 8. Unresolved decisions this touched but did not settle

Reported rather than invented (ground rule 3). All still open in
`docs/OPEN-DECISIONS.md`:

* **E1 — GPU host, Modal vs RunPod.** Untouched. Worth noting that the exit
  stays cheap: `api.py` dispatches through a single
  `Function.from_name(...).spawn()`, so a second backend is one dispatch
  function, not a rewrite. Keep it that way.
* **D5 — accounts.** `users`, `creator_tokens` and `sessions` exist in the
  schema because `identity-and-analytics.md` §4 resolved the *shape* (optional
  accounts, anonymous by default, a creator token — not a user — owns a
  lesson). No code writes them. Magic-link auth is migration step 10, last,
  because it is the only step that is product-visible.
* **D6 / D7.** The schema has `last_access_at`, `removed_at` and
  `removed_reason`; the live behaviour is still `retention.py` against Volumes,
  unchanged and not reinvented. The migration preserves it rather than replacing
  it.
* **E7 — 15 fps vs 30 fps.** Its own entry says to decide after
  `caching-retention` lands, which it now has. Not decided here; it is a cost
  decision, not a deployment one.

## 9. What was not done, and why

* **Migration step 4** (worker writes Postgres directly) — §5.1. Risking the
  pinned GPU images for a path that is already correct, before the database
  exists, is a bad trade.
* **Migration step 6** (presigned browser uploads straight to R2) — real, and
  cheap once the API stops handling video bytes, but it changes the `POST
  /clips` contract from multipart to a key, and `apps/web` has no deploy yet to
  change with it.
* **Migration steps 8–11** (frontend, Sentry/monitors, magic link, dedupe on the
  DB index) — all downstream of a credential that does not exist.
* **Cloudflare cache purge on delete** — §5.2, needs an API token.
* **Better Stack monitors** — free, but there is no domain to monitor yet and no
  Sentry to route to. Three monitors and one heartbeat on the sweeper cron, per
  infrastructure.md §7, when there is.
