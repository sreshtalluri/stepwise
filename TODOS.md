# Stepwise TODOs

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

### Full Hand Joint Rendering (21 joints per hand)
Add toggleable detailed hand skeleton view alongside the simplified hand shapes (fist/open/spread). Shows all 21 finger joints per hand for subtle details — finger tutting, hand fans, wave motions. Toggle in the detail bar.
- **Effort:** S (human: ~3 days / CC: ~30 min)
- **Depends on:** MediaPipe Hands integration working, viewer rendering hands
- **Context:** Added during CEO review #2 (2026-03-18). Simplified shapes cover most learning needs but some choreography has subtle finger details that need full joint visibility.

### Webcam Feedback Loop
Record yourself dancing via webcam, see your pose overlaid on the original dancer's pose with scoring. The "AI dance coach" — turns Stepwise from a viewer into a learning product.
- **Effort:** L (human: ~6 weeks / CC: ~6-8 hours)
- **Depends on:** Core viewer must be solid. Pose comparison (DTW algorithm) needs its own research spike.
- **Context:** This is Approach B from the original design doc. The defensibility moat — much harder to replicate than just a viewer.

## P2

### Full Design System (DESIGN.md)
Run /design-consultation to create a comprehensive design system: component library, animation guidelines, brand voice, icon style, motion principles. Prevents design drift as features are added.
- **Effort:** M (human: ~3 days / CC: ~30 min)
- **Depends on:** Nothing — can run anytime
- **Context:** Added during design review (2026-03-18). Minimal design tokens (dark + neon, cyan accent, Inter/Space Grotesk, 4px spacing) are defined for v1, but a full system prevents inconsistency in v2+.

### Upgrade Polling to Server-Sent Events (SSE)
Replace GET /api/status polling (every 2-3s) with SSE for real-time progress updates. Frontend opens a persistent connection and receives status changes as they happen ('downloading...', 'extracting poses...', 'done!').
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Core polling must be working first
- **Context:** Added during eng review (2026-03-18). Polling works but SSE gives better UX — no 2-3s delay between updates, fewer HTTP requests, enables richer progress indicators.

## P3

### Skeleton Style Picker
Let users choose skeleton visual style: neon wireframe, realistic mannequin, minimal stick figure, cartoon character. Cosmetic personalization that adds personality and shareability.
- **Effort:** S (human: ~2 days / CC: ~20 min)
- **Depends on:** Core Three.js rendering working
- **Context:** Deferred from CEO plan review (2026-03-18). Different Three.js materials/meshes for the same skeleton data.
