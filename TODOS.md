# Stepwise TODOs

## P0

### Production Adapter Spike
- Implement and benchmark one real `PersonDetector`, `PersonTracker`, and `MeshRecoverer` adapter.
- Document exact licenses in `docs/models/` before enabling any production deployment.
- Keep the mock adapters for CI and local deterministic tests.

### Storage + Upload Integration
- Finish production verification of Cloudflare R2 bucket CORS and presigned upload credentials.
- Support uploaded video references as well as source URLs. (Initial R2/S3-compatible adapter and presigned upload API are in place.)
- Preserve partial result packaging if one person's mesh recovery fails.

### Durable Jobs + Workers
- Replace `InMemoryJobStore` with Railway Postgres-backed state.
- Split Railway deployment into API web service and worker service.
- Persist state transitions, result object keys, failures, retry counts, and model warnings.

### GLB Export Validation
- Export animated skinned mesh assets as GLB.
- Validate output with a standard glTF validator.

## P1

### Browser QA Pass
- Run desktop, tablet, and mobile browser verification for landing, processing, viewer, ghost, mirror, person switching, speed/loop, and timeline controls.

### Model Benchmarks
- Benchmark solo dance, two-person crossing, and group choreography fixtures on target GPU hardware.

### Real Analysis Upgrades
- Replace mock beats/difficulty/path trails with production beat detection and movement analysis.

## P2

### Shareable Clips
- Render short watermarked mesh/video clips for social sharing.

### Webcam Feedback Loop
- Compare user webcam motion to the recovered mesh timeline.
