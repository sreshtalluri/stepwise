# Mesh Adapter Install Notes

## Local Development

The checked-in v1 runs without model weights:

```bash
cd services/mesh-api
PYTHONPATH=src uvicorn mesh_api.app:app --reload
```

The mock adapters produce deterministic multi-person tracks, partial-failure cases, stylized humanoid rest meshes, and per-frame transforms. They are intended for contracts, UI, API integration, and CI.

## API Ingest Paths

URL/social video path:

```bash
curl -X POST http://localhost:8000/v1/jobs \
  -H 'content-type: application/json' \
  -d '{"source_url":"https://www.youtube.com/watch?v=demo"}'
```

Raw video bytes path for already-downloaded videos:

```bash
curl -X POST http://localhost:8000/v1/jobs/upload \
  -H 'content-type: video/mp4' \
  -H 'x-filename: dance.mp4' \
  --data-binary @dance.mp4
```

In production, the URL path should download/transcode/probe with `yt-dlp` + FFmpeg/ffprobe, store the normalized clip in object storage, and pass local video bytes or a storage reference to the CV pipeline.

## Production GPU Path

Recommended deployment defaults remain compatible with Modal + R2:

- Run `services/mesh-api` on a GPU worker.
- Store uploaded/transcoded videos, mesh JSON, optional GLB, and debug overlays in object storage.
- Use signed URLs in `MeshResultV1.assets`.
- Keep `MAX_VIDEO_SECONDS=120` and `TARGET_MESH_FPS=24` unless benchmarks justify changing them.

## Adapter Work Items

1. Add a concrete adapter module under `services/mesh-api/src/mesh_api/adapters/`.
2. Implement the protocol from `base.py`.
3. Add adapter unit tests and fixtures.
4. Add a benchmark row in `benchmark-results.md`.
5. Update `model-selection.md` with license and production notes.
