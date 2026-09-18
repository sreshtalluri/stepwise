# Stepwise — Project Status

**Last updated:** 2026-06-23 (mesh platform restart implementation)

## What's Implemented on `feat/mesh-platform-restart`

- **Repo restart structure** — `apps/web`, `services/mesh-api`, `packages/contracts`, and `docs/models`.
- **MeshResultV1 contract** — JSON schema, generated TypeScript types, and fixtures for single-person, multi-person, partial-failure, and no-person cases.
- **FastAPI mesh service** — health, model inventory, async-style job lifecycle, job result endpoint, adapter protocols, deterministic mock detector/tracker/mesh recoverer, partial-result policy, max-duration validation, no-people failure.
- **Storage/deployment path** — S3-compatible object storage adapter, presigned upload endpoint, raw upload persistence, signed result asset URLs, CORS support for Vercel → Railway calls, Railway service config, and Vercel/Railway/R2/Modal deployment doc.
- **Next.js web app** — dark/cyan Stepwise landing/upload, processing stages, and multi-person mesh viewer with React Three Fiber skinned body surfaces.
- **Viewer controls** — person selector, primary dancer auto-focus, all-person view, side-by-side, ghost, mirror/back, formation minimap, freeze/orbit, X-ray debug overlay, speed/loop controls, difficulty/body-part heatmap, step markers, path trail summaries.
- **Model documentation** — adapter candidates, license gate, install notes, and benchmark placeholders.

## Important Process Deviation

The original plan requested human approval of visual concepts before implementation. This handoff requested direct implementation, so code-native concepts were documented in `docs/designs/mesh-platform-restart-concepts.md` without a separate approval round.

## Next Steps

1. Replace the development `InMemoryJobStore` with Railway Postgres and add a separate worker service.
2. Add real GPU adapters behind the existing protocols after license review, starting with a Modal `MeshRecoverer` adapter.
3. Add real URL ingest/transcode worker support with `yt-dlp` + `ffprobe` and platform ToS review.
4. Add GLB export and glTF validation.
5. Add browser automation QA screenshots for desktop/tablet/mobile once a dev server is approved to run.
