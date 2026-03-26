# Stepwise

Upload any dance video, get an interactive 3D step-by-step breakdown — synced to the beat, viewable from any angle.

## How It Works

1. **Paste a URL** — TikTok, Instagram Reels, or YouTube
2. **Pipeline processes** — downloads video, extracts 3D pose with MediaPipe, detects beats, analyzes difficulty
3. **Interactive viewer** — 8 view presets, ghost overlay, timeline with loop/speed controls

## Architecture

```
Frontend (Next.js 14 + Three.js)     Pipeline (Python/FastAPI on Modal)
┌─────────────────────────┐          ┌──────────────────────────┐
│ Landing page             │          │ yt-dlp download          │
│ Viewer (8 presets)       │◄────────►│ MediaPipe Pose Landmarker│
│ Timeline + beat markers  │  API     │ Beat detection (librosa) │
│ Ghost overlay (2D canvas)│          │ Difficulty scoring       │
│ 3D skeleton (Three.js)   │          │ Foot contact heuristic   │
└─────────────────────────┘          │ R2 storage (pose + video)│
                                     └──────────────────────────┘
```

## View Presets

| # | Name | Description |
|---|------|-------------|
| 1 | Front | Full-screen front skeleton view |
| 2 | Mirror | Mirrored skeleton (practice facing) |
| 3 | Side by Side | Original video + front skeleton (default) |
| 4 | Front + Back | Front and back skeleton views |
| 5 | Ghost | Skeleton overlaid on dimmed video (2D canvas, pixel-perfect) |
| 6 | Video + PiP | Full video with skeleton picture-in-picture |
| 7 | Freeze | Pause to orbit/rotate the skeleton in 3D |
| 8 | Split Mirror | Front + mirrored side by side |

## Dual Coordinate System

The pipeline outputs two coordinate sets per frame:
- **`joints`** — image-space coordinates for pixel-perfect ghost overlay alignment
- **`joints_3d`** — world-blended coordinates for correct 3D body proportions in perspective views

## Tech Stack

- **Frontend:** Next.js 14, React Three Fiber, Three.js, Tailwind CSS
- **Pipeline:** Python, FastAPI, MediaPipe Pose Landmarker, librosa, yt-dlp
- **Infrastructure:** Modal (serverless GPU), Cloudflare R2 (storage)
- **Design:** Clash Grotesk + Instrument Sans + Geist Mono, dark theme with cyan accent

## Development

```bash
# Frontend
cd frontend && npm install && npm run dev

# Pipeline (local)
cd pipeline && pip install -r requirements.txt
modal serve pipeline/modal_app.py

# Pipeline (deploy)
modal deploy pipeline/modal_app.py
```

## Project Status

See [TODOS.md](TODOS.md) for the full roadmap and prioritized backlog.
