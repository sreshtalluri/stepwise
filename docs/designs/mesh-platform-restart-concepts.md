# Mesh Platform Restart — Visual Concepts

> Process note: the implementation handoff requested immediate execution. I generated these code-native concepts from the plan, user corrections, and existing Stepwise design system, but I did not receive a separate human visual-approval checkpoint before coding.

## Corrected Direction

The first mock mesh was too boxy. The corrected target is a stylized dance-training body: smooth, simplified, readable, closer to a Wii Fit Trainer / Just Dance / Swayformations-style performer than a raw skeleton or cuboid. The mock mesh now uses separate smooth humanoid body volumes for torso, neck, head, arms, legs, and feet, with a richer joint hierarchy and skin weights.

## Concept A — Landing / Upload

- **Mood:** motion-capture lab at 2am: black grid field, restrained cyan glow, technical but dance-first.
- **Layout:** split first viewport. Left side is the primary promise and URL/upload form. Right side is the pipeline proof card.
- **Core UI:** paste YouTube/TikTok/Instagram/direct URL or upload an already-downloaded video. No manual seconds input.
- **Pipeline message:** link download/probe → YOLO detector → ID tracker → humanoid mesh.

## Concept B — Processing

- **Mood:** GPU job console, but readable for consumer users.
- **Layout:** centered status panel with the current stage in large display type, segmented stages in a two-column grid, progress bar, detected people count, and warnings.
- **Stages:** queued, downloading, detecting, tracking, meshing, skinning, smoothing, analyzing, packaging, complete.
- **Behavior:** local mock job advances through each stage so the UX can be tested without live GPU adapters.

## Concept C — Viewer

- **Mood:** multi-panel choreography analysis tool.
- **Layout:** left control rail, central video/mesh surface, right timeline/analysis rail.
- **Primary representation:** React Three Fiber renders animated skinned humanoid body surfaces per mesh-bearing person. X-ray skeleton points are only a debug overlay.
- **Controls:** person selector, primary-dancer auto-focus, all-person view, side-by-side, ghost, front, back, formation/minimap, mirror, X-ray, freeze/orbit, speed, loop end.
- **Analysis:** difficulty heatmap, body-part heatmap, step markers, hand/foot trail summaries, and license warning card.

## Design Tokens Used

- Background: `#0a0a0a`
- Surface: `#141414`
- Border: `#222222`
- Accent: `#00d4ff`
- Success: `#44ff88`
- Warning: `#ffdd44`
- Error: `#ff4444`
- Display font: Clash Grotesk
- Body font: Instrument Sans
- HUD font: Geist Mono
