# Production Adapter Plan

## Ingest

Use `YtDlpFfmpegVideoIngestor` from `services/mesh-api/src/mesh_api/adapters/video.py` on GPU workers that include:

- `yt-dlp` for YouTube/TikTok/Instagram/direct URL downloading.
- `ffprobe` for real duration/FPS/resolution detection.
- Object storage resolution for `upload://` references.

The website submits links or uploaded files. The API owns all duration probing and must reject videos above `MAX_VIDEO_SECONDS` after probing the actual media.

## Detection / Tracking

Use `UltralyticsYoloPersonDetector` from `services/mesh-api/src/mesh_api/adapters/yolo.py` only after license review. It is behind `PersonDetector` so it can be replaced by another detector if AGPL/Enterprise terms are not acceptable.

## Mesh Recovery

Next concrete adapter should be one of:

1. SAM 3D Body + MHR for full-body body/feet/hands mesh recovery.
2. 4D Humans / HMR 2.0 for video reconstruction and tracking through occlusion.
3. Multi-HMR 2 as a research adapter once install/license stability is verified.

The rendered output should remain a stylized, trainer-like body surface. Production recovery can either emit the final surface directly or fit/retarget recovered pose and shape onto a consistent Stepwise training mesh.
