# Stepwise TODOs

## Completed (recent)

### ~~Ghost Overlay Alignment~~ — RESOLVED
**Resolved:** 2026-03-26. Ghost mode now uses a 2D HTML Canvas overlay instead of Three.js orthographic camera. Pipeline outputs dual coordinates: image-space (for ghost pixel alignment) and world-blended (for 3D perspective views). Skeleton aligns perfectly with dancer in video for both portrait and landscape formats.

### ~~Video Playback from R2~~ — RESOLVED
**Resolved:** 2026-03-20. Videos uploaded to R2 after processing. Frontend plays video from R2 signed URL. Cost: ~$0.015/GB/month (negligible).

### ~~View Labels~~ — RESOLVED
**Resolved:** 2026-03-20. All 8 view presets now have HUD-style labels (Geist Mono, semi-transparent) identifying each panel.

### ~~SMPL-X License Research~~ — RESOLVED
**Resolved:** 2026-03-19. SMPL, SMPL-X, and STAR are ALL non-commercial (MPI license). Commercial license available from Meshcapade. Strategy: build with custom geometric mannequin mesh, swap to SMPL-X if license secured.

### ~~Full Hand Joint Rendering~~ — RESOLVED
**Resolved by:** SMPL-X mannequin upgrade (CEO review 2026-03-19). SMPL-X includes 21 hand joints per hand natively.

## P0

_No P0 items currently._

## P1

### Shareable Clip Generation
Generate 5-15 second clips (ghost mode or 3D skeleton) with "Made with Stepwise" watermark for TikTok/Instagram sharing. Primary distribution mechanism — users share clips, others discover Stepwise organically.
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** Core viewer + ghost mode working ✅
- **Context:** Deferred from CEO plan review (2026-03-18). Server-side video rendering via FFmpeg.

### Advanced Foot Contact Detection (Video Frame Analysis)
Upgrade foot contact from pose heuristic (v1) to optical flow analysis on the foot region of each video frame. Detects slides, toe-work, heel-toe transitions that the heuristic misses. Critical for styles like moonwalk, popping, locking.
- **Effort:** M (human: ~2 weeks / CC: ~2 hours)
- **Depends on:** Core pipeline + v1 foot contact heuristic working ✅
- **Context:** Added during CEO review #2 (2026-03-18).

### Webcam Feedback Loop
Record yourself dancing via webcam, see your pose overlaid on the original dancer's pose with scoring. The "AI dance coach" — turns Stepwise from a viewer into a learning product.
- **Effort:** L (human: ~6 weeks / CC: ~6-8 hours)
- **Depends on:** Core viewer must be solid ✅. Pose comparison (DTW algorithm) needs its own research spike.
- **Context:** This is the defensibility moat — much harder to replicate than just a viewer.

## P2

### Slow-Mo Isolation View
When looping a section, camera auto-zooms to the body part that moves most. Learning a hand wave? Camera zooms to hands. Footwork? Camera drops to feet.
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** View presets working ✅, joint velocity data available ✅

### Floor Path View
Top-down view showing just the feet with a trail line showing where the dancer travels across the floor over time. For stage choreography and formations.
- **Effort:** S (human: ~3 days / CC: ~30 min)
- **Depends on:** Foot contact data ✅, pose data with position tracking ✅

### Quad View (Power User)
2x2 grid showing Front, Back, Mirror, and Video simultaneously.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** View presets working ✅

### Full Design System (DESIGN.md)
Run /design-consultation to create comprehensive design system: component library, animation guidelines, brand voice, icon style, motion principles.
- **Effort:** M (human: ~3 days / CC: ~30 min)
- **Depends on:** Nothing — can run anytime

### Person Tracking Confidence Indicator
When tracking confidence drops (e.g., during dancer occlusion), show a visual indicator. Prevents silent failure of person ID swaps.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Multi-person tracking (SMPL-X) + formation minimap

### Comparison Ghost (Dual Mannequin Overlay)
Overlay two different dancers' mannequins to see style differences. Load two videos of the same choreo, see both mannequins simultaneously, color-coded.
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** Mannequin renderer + multi-person working

### Upgrade Polling to Server-Sent Events (SSE)
Replace GET /api/status polling with SSE for real-time progress updates.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Core polling working ✅

## P3

### Mannequin Color Themes
Let users pick the mannequin's visual theme: cyan holographic (default), white porcelain, matte black, holographic rainbow.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Mannequin renderer working (SMPL-X upgrade)
