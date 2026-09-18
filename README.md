# Stepwise Mesh Platform

Upload a dance video and get a synchronized, multi-person **full-body mesh** breakdown: original video, skinned body surfaces, beat markers, path trails, difficulty heatmaps, and debug skeleton overlays.

This branch is a restart from the old skeleton/mannequin direction. The default v1 output is a renderable skinned body surface per person, not a stick figure and not a fixed generic avatar driven only by pose rotations.

## Repository Structure

```text
apps/web/                 Next.js + React Three Fiber app
services/mesh-api/         FastAPI mesh processing service
packages/contracts/        MeshResultV1 JSON schema, fixtures, generated TS types
docs/models/               model selection, license, install, benchmark notes
docs/designs/              preserved and new design docs
```

## Architecture

```text
Video URL / upload reference
  → services/mesh-api POST /v1/jobs
  → optional Cloudflare R2 direct upload via POST /v1/uploads/presign
  → validate + transcode gate
  → PersonDetector adapter (YOLO-style front door)
  → PersonTracker adapter (persistent track IDs)
  → MeshRecoverer adapter (rest-pose skinned body mesh per person)
  → smoothing + movement analysis + partial-result packaging
  → MeshResultV1 contract
  → apps/web skinned mesh playback with React Three Fiber
```

## API Endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/uploads/presign`
- `POST /v1/jobs`
- `POST /v1/jobs/upload`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/result`

Job stages are: `queued`, `downloading`, `detecting`, `tracking`, `meshing`, `skinning`, `smoothing`, `analyzing`, `packaging`, `complete`, `failed`.

## Development

```bash
# all tests
npm test

# contracts only
npm run test:contracts

# API only
npm run test:api

# web tests/build
npm run test:web
npm run build:web

# local services
npm run dev:api
npm run dev:web
```

## Current Implementation

- Deterministic mock CV adapters for local development and CI.
- S3-compatible object storage adapter for Cloudflare R2 production and in-memory local tests.
- Presigned upload flow so browser users can upload video files directly to object storage before job creation.
- Multi-person result contract with per-person `track_id`, color, confidence, frame coverage, primary-dancer score, mesh asset, and partial-failure support.
- Inline rest-pose mesh assets include vertices, faces, skin weights, joint hierarchy, inverse bind matrices, shape parameters, and source model.
- Web viewer includes landing/upload, processing stages, side-by-side video/mesh, ghost mode, mirror/back views, formation minimap, freeze/orbit, X-ray skeleton overlay, speed/loop controls, beat/difficulty/body-part/step/path UI.

## Production Notes

The model stack is intentionally adapter-based. Before enabling production detectors or mesh recoverers, document their exact licenses in `docs/models/` and expose `LicenseFlag` entries via `/v1/models` and `MeshResultV1.model_report`.

Deployment target: `apps/web` on Vercel, `services/mesh-api` on Railway, Cloudflare R2 for video/result assets, Modal for GPU model workers, and Railway Postgres for durable job state. See `docs/deployment/vercel-railway-cloudflare-modal.md`.
