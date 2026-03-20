# Stepwise TODOs

## P0

### ~~SMPL-X License Research~~ — RESOLVED
**Resolved:** 2026-03-19. SMPL, SMPL-X, and STAR are ALL non-commercial (MPI license). STAR is NOT MIT/Sony — same MPI group. Commercial license available from Meshcapade (sales@meshcapade.com). Pricing inquiry sent. Strategy: build with custom geometric mannequin mesh, swap to SMPL-X if license secured.

## P1

### Shareable Clip Generation
Generate 5-15 second clips (ghost mode or 3D skeleton) with "Made with Stepwise" watermark for TikTok/Instagram sharing. Primary distribution mechanism — users share clips, others discover Stepwise organically.
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** Core viewer + ghost mode working
- **Context:** Deferred from CEO plan review (2026-03-18). This is Approach C from the original design doc, reframed as a feature within Approach A. Server-side video rendering via FFmpeg.

### Advanced Foot Contact Detection (Video Frame Analysis)
Upgrade foot contact from pose heuristic (v1) to optical flow analysis on the foot region of each video frame. Detects slides, toe-work, heel-toe transitions that the heuristic misses. Critical for styles like moonwalk, popping, locking.
- **Effort:** M (human: ~2 weeks / CC: ~2 hours)
- **Depends on:** Core pipeline + v1 foot contact heuristic working
- **Context:** Added during CEO review #2 (2026-03-18). The pose heuristic captures ~80% of contact types. This upgrade adds video analysis for the remaining 20% — which is often the most interesting footwork.

### ~~Full Hand Joint Rendering (21 joints per hand)~~ — RESOLVED
**Resolved by:** SMPL-X mannequin upgrade (CEO review 2026-03-19). SMPL-X includes 21 hand joints per hand natively — no separate implementation needed.

### Webcam Feedback Loop
Record yourself dancing via webcam, see your pose overlaid on the original dancer's pose with scoring. The "AI dance coach" — turns Stepwise from a viewer into a learning product.
- **Effort:** L (human: ~6 weeks / CC: ~6-8 hours)
- **Depends on:** Core viewer must be solid. Pose comparison (DTW algorithm) needs its own research spike.
- **Context:** This is Approach B from the original design doc. The defensibility moat — much harder to replicate than just a viewer.

## P2

### Slow-Mo Isolation View
When looping a section, camera auto-zooms to the body part that moves most. Learning a hand wave? Camera zooms to hands. Footwork? Camera drops to feet. Like a dance teacher saying "watch my feet here."
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** View presets working, joint velocity data available (already computed for difficulty)
- **Context:** Deferred from CEO review #3 (2026-03-19). Requires mapping which joints have highest velocity in the looped section and animating camera position.

### Floor Path View
Top-down view showing just the feet with a trail line showing where the dancer travels across the floor over time. For stage choreography and formations.
- **Effort:** S (human: ~3 days / CC: ~30 min)
- **Depends on:** Foot contact data, pose data with position tracking
- **Context:** Deferred from CEO review #3 (2026-03-19). Answers "where am I supposed to be standing?" — critical for stage choreography.

### Quad View (Power User)
2x2 grid showing Front, Back, Mirror, and Video simultaneously. For power users who want everything at once.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** View presets working
- **Context:** Deferred from CEO review #3 (2026-03-19). Replaces the modular grid but as a single curated preset.

### Full Design System (DESIGN.md)
Run /design-consultation to create a comprehensive design system: component library, animation guidelines, brand voice, icon style, motion principles. Prevents design drift as features are added.
- **Effort:** M (human: ~3 days / CC: ~30 min)
- **Depends on:** Nothing — can run anytime
- **Context:** Added during design review (2026-03-18). Minimal design tokens (dark + neon, cyan accent, Inter/Space Grotesk, 4px spacing) are defined for v1, but a full system prevents inconsistency in v2+.

### Person Tracking Confidence Indicator
When 4D Humans tracking confidence drops (e.g., during dancer occlusion), show a visual indicator on the formation minimap — pulsing dot or amber warning badge. Prevents silent failure of person ID swaps going unnoticed.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Multi-person tracking (SMPL-X Phase 1) + formation minimap (Phase 3) both shipping
- **Context:** Added during eng review (2026-03-19). Person ID swap is a silent failure — the user wouldn't know their focused dancer swapped identity. This makes tracking quality visible.

### Comparison Ghost (Dual Mannequin Overlay)
Overlay two different dancers' mannequins to see style differences. Load two videos of the same choreo and see both mannequins simultaneously, color-coded. Shows where movement diverges.
- **Effort:** M (human: ~1 week / CC: ~1 hour)
- **Depends on:** Mannequin renderer + multi-person working
- **Context:** Deferred from CEO review (2026-03-19). Precursor to Webcam Feedback Loop but using pre-recorded video instead of live input. Requires temporal alignment of two pose datasets.

### Upgrade Polling to Server-Sent Events (SSE)
Replace GET /api/status polling (every 2-3s) with SSE for real-time progress updates. Frontend opens a persistent connection and receives status changes as they happen ('downloading...', 'extracting poses...', 'done!').
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Core polling must be working first
- **Context:** Added during eng review (2026-03-18). Polling works but SSE gives better UX — no 2-3s delay between updates, fewer HTTP requests, enables richer progress indicators.

## P3

### Mannequin Color Themes
Let users pick the mannequin's visual theme: cyan holographic (default), white porcelain, matte black, holographic rainbow. Cosmetic personalization that adds shareability.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Mannequin renderer working (SMPL-X upgrade)
- **Context:** Merged from "Skeleton Style Picker" (CEO review 2026-03-18) and "Mannequin Color Themes" (CEO review 2026-03-19). The mannequin replaces the skeleton as the primary visual — themes apply to it instead.





Current flow:
yt-dlp downloads video → processes locally on Modal → saves pose JSON to
R2 → discards video file

Production flow:
yt-dlp downloads video → processes locally on Modal → saves pose JSON to
R2 → ALSO uploads video MP4 to R2 → frontend plays video from R2 signed
URL

What needs to change:
1. storage.py — add an upload_video() function (same R2 bucket, key
pattern: {url_hash}/video.mp4)
2. app.py — after processing, upload the video file to R2 and include the
signed URL in the result
3. Frontend — already set up to receive video_url, no changes needed

Cost: R2 has no egress fees. Storage is $0.015/GB/month. A 15-second
TikTok video is ~1.5MB. You'd need 700 videos to hit 1GB ($0.015/month).
Basically free.

Time to implement: ~15 minutes with CC.

One consideration: You'd want a TTL/cleanup job eventually (delete videos
older than 30 days, same as pose data). But that's a future
optimization, not a blocker.