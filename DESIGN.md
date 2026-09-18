# Design System — Stepwise Mesh Platform

## Product Context

- **What this is:** A movement learning platform that turns dance videos into synchronized full-body skinned mesh playback.
- **Who it's for:** Dancers learning choreography from social videos, group choreographers reviewing formations, and creators who need clear movement breakdowns.
- **V1 principle:** The primary output is a body surface for each person. Skeletons are debug/X-ray overlays only.

## Aesthetic Direction

- **Direction:** Retro-futuristic motion-capture lab with restrained dance energy.
- **Mood:** dark, precise, kinetic, and technical without feeling like enterprise software.
- **Visual idea:** cyan skinned body surfaces and HUD-like analysis panels over a black grid field.

## Typography

- **Display/Hero:** Clash Grotesk, 600/700.
- **Body/UI:** Instrument Sans, 400/500/600/700.
- **HUD/Data:** Geist Mono, 400/500/600.

## Color

- Background: `#0a0a0a`
- Surface: `#141414`
- Surface hover: `#1a1a1a`
- Border: `#222222`
- Text primary: `#f0f0f0`
- Text secondary: `#888888`
- Accent: `#00d4ff`
- Success: `#44ff88`
- Warning: `#ffdd44`
- Error: `#ff4444`

## Component Patterns

- **Landing upload panel:** URL input, upload reference control, clip-length warning, primary cyan CTA.
- **Processing panel:** large current stage, segmented stage grid, progress bar, detected people count, warnings.
- **Viewer shell:** left controls, central mesh/video stage, right timeline/analysis rail.
- **Mesh canvas:** dark WebGL canvas, cyan/green person surfaces, floor grid, optional orbit controls.
- **Timeline:** scrubber, speed buttons, loop range, beat/difficulty visualization.
- **Debug overlays:** X-ray skeleton points and debug overlays may be toggled, but never replace the skinned mesh surface as the primary representation.

## Motion

- Micro-interactions: 100–150ms hover/selection changes.
- Processing stage progression: deterministic local mock timing for frontend development.
- Mesh animation: browser-side linear blend skinning from rest mesh + per-frame pose/global transforms.
