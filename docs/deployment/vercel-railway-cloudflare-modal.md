# Deployment Plan — Vercel + Railway + Cloudflare R2 + Modal

This is the production target for the mesh restart.

## Responsibility split

```text
apps/web on Vercel
  - landing/upload/process/viewer UI
  - browser calls Railway API via NEXT_PUBLIC_MESH_API_URL
  - browser uploads large video files directly to Cloudflare R2 using presigned PUT URLs

services/mesh-api on Railway
  - FastAPI control plane
  - validates URL/upload refs
  - probes/downloads/transcodes video
  - creates/updates jobs
  - writes result manifests and mesh assets to R2
  - calls Modal GPU workers through a MeshRecoverer adapter

Cloudflare R2
  - source uploads
  - normalized/transcoded videos
  - mesh JSON/GLB/debug overlays
  - signed GET URLs for viewer assets

Modal
  - GPU model execution for detector/tracker/mesh recovery spikes
  - first production candidates: YOLO-style detector/tracker + SAM 3D Body/MHR or 4D Humans adapter

Railway Postgres
  - durable jobs, state transitions, result object keys, adapter warnings
  - replaces the current in-memory development store before public launch
```

## What is wired now

- `POST /v1/uploads/presign` returns a `storage://...` upload reference plus a presigned `PUT` target.
- `POST /v1/jobs/upload` stores raw uploaded bytes in object storage before creating a job.
- Completed jobs write:
  - `results/{job_id}/mesh-result-v1.json`
  - `results/{job_id}/meshes/{track_id}.mesh.json`
  - signed asset URLs in `MeshResultV1.assets`
- The web app uses `NEXT_PUBLIC_MESH_API_URL` when set. If it is unset, the app stays in deterministic fixture/mock mode for local UI work.
- The API has CORS support through `CORS_ORIGINS`.

## Required environment variables

### Vercel — `apps/web`

```bash
NEXT_PUBLIC_MESH_API_URL=https://<railway-api-domain>
```

### Railway — `services/mesh-api`

```bash
MAX_VIDEO_SECONDS=120
TARGET_MESH_FPS=24
CORS_ORIGINS=https://<vercel-domain>,http://localhost:3000

STORAGE_BACKEND=r2
S3_ENDPOINT_URL=https://<cloudflare-account-id>.r2.cloudflarestorage.com
S3_REGION=auto
S3_BUCKET=stepwise-mesh
S3_ACCESS_KEY_ID=<r2-access-key>
S3_SECRET_ACCESS_KEY=<r2-secret-key>

DATABASE_URL=<railway-postgres-url>

MODAL_GPU_WORKER_URL=<modal-web-endpoint>
MODAL_GPU_WORKER_TOKEN=<shared-secret>
```

### Modal

Use `scripts/setup_modal_secrets.sh` after populating `.env` with the `S3_*` variables.

## Cloudflare R2 bucket CORS

Direct browser uploads to presigned R2 URLs require bucket CORS. Use the Vercel domains plus localhost during development:

```json
[
  {
    "AllowedOrigins": [
      "https://<vercel-domain>",
      "http://localhost:3000"
    ],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedHeaders": ["Content-Type", "x-amz-*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

## Railway deployment

Deploy `services/mesh-api` as its own Railway service with the service root set to `services/mesh-api`. The checked-in `railway.json` starts the app with:

```bash
PYTHONPATH=src uvicorn mesh_api.app:app --host 0.0.0.0 --port $PORT
```

Add a Railway Postgres service before public traffic. The code still uses `InMemoryJobStore`, so this branch should not be treated as concurrency-safe until the Postgres-backed job repository and a separate worker process are implemented.

## Vercel deployment

Deploy `apps/web` as the Vercel project root directory. Set:

```bash
NEXT_PUBLIC_MESH_API_URL=https://<railway-api-domain>
```

Because the browser calls Railway directly, do not proxy large uploads through Vercel Functions.

## Next implementation cut

1. Add Postgres job persistence and migrations.
2. Split Railway into a web service and worker service.
3. Add a Modal `MeshRecoverer` adapter that accepts storage keys and writes recovered mesh assets back to R2.
4. Add URL ingest worker support with `yt-dlp`/`ffprobe`, including platform Terms-of-Service review.
5. Add production model license checks before enabling any real YOLO/HMR/SAM adapter by default.
