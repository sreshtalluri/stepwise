# Design System — Stepwise

## Product Context
- **What this is:** A movement learning platform that turns any video into an interactive 3D skeleton breakdown
- **Who it's for:** TikTok dancers and K-pop fans learning choreography from social media videos
- **Space/industry:** Dance learning / movement analysis — between consumer dance apps (Steezy) and professional motion capture tools (Vicon)
- **Project type:** Web app (viewer/tool) with a marketing landing page

## Aesthetic Direction
- **Direction:** Retro-Futuristic meets Industrial — dark, precise, but with kinetic energy
- **Decoration level:** Intentional — subtle grid pattern background, glow effects on interactive elements, no gratuitous gradients or stock patterns
- **Mood:** Motion capture lab at 2am, neon markers glowing. Technical precision with dance culture energy. Not sterile like Vicon, not bubbly like Steezy.
- **Reference sites:** Vicon (dark/industrial baseline), Steezy (dance learning conventions to learn from but not copy)

## Typography
- **Display/Hero:** Clash Grotesk (700/600) — geometric, sharp, distinctive. The brand voice. Used for the "stepwise" wordmark, page headings, camera angle labels. Loaded from FontShare.
- **Body:** Instrument Sans (400/500/600) — clean, readable, slightly warmer than Inter. Used for paragraphs, UI labels, button text. Loaded from Google Fonts.
- **UI/Labels:** Same as body (Instrument Sans 500)
- **Data/Tables:** Geist Mono (400/500) — timestamps, speed badges, step counters, processing status, technical readouts. Supports tabular-nums. The "HUD" font.
- **Code:** Geist Mono
- **Loading:** Clash Grotesk via FontShare CDN, Instrument Sans + Geist Mono via Google Fonts
- **Scale:**
  - xs: 12px (panel labels, meta text)
  - sm: 14px (camera buttons, badges, captions)
  - base: 16px (body text minimum, inputs)
  - lg: 18px (subtitle, input text)
  - xl: 20px (section subheadings)
  - 2xl: 28px (display sub, feature headings)
  - 3xl: 36px (section titles)
  - 4xl: 48px (hero mobile)
  - 5xl: 72px (hero desktop)

## Color
- **Approach:** Restrained — one accent + neutrals. Color is rare and meaningful. Cyan = interactive or skeleton. No competing accents.
- **Primary/Accent:** #00d4ff (electric cyan) — the skeleton color, active states, links, focus rings, interactive elements
- **Accent Glow:** rgba(0, 212, 255, 0.2) — hover states, active button shadows, focus ring glow
- **Accent Subtle:** rgba(0, 212, 255, 0.08) — ghost button hover, subtle backgrounds
- **Neutrals (cool grays):**
  - Background: #0a0a0a
  - Surface: #141414 (panels, cards, camera bar)
  - Surface Hover: #1a1a1a
  - Border: #222222
  - Text Tertiary: #555555
  - Text Secondary: #888888
  - Text Primary: #f0f0f0
- **Semantic:**
  - Success: #44ff88 (also used for "easy" difficulty)
  - Warning: #ffdd44 (also used for "medium" difficulty)
  - Error: #ff4444 (also used for "hard" difficulty)
  - Info: #00d4ff (same as accent)
- **Heatmap gradient:** #44ff88 → #ffdd44 → #ff4444 (difficulty timeline)
- **Foot contact colors:** green=#44ff88 (flat), yellow=#ffdd44 (heel), orange=#ff8844 (toe), blue=#00d4ff (slide), none (airborne)
- **Dark mode:** This IS dark mode. No light mode for v1. Dark backgrounds make the cyan skeleton pop — this is why every motion capture tool uses dark.
- **Contrast ratios:**
  - Cyan (#00d4ff) on dark (#0a0a0a): 11.18:1 (AAA)
  - Secondary text (#888) on dark (#0a0a0a): 5.58:1 (AA)
  - Primary text (#f0f0f0) on dark (#0a0a0a): 17.37:1 (AAA)

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — not cramped (it's a learning tool, not a data dashboard)
- **Scale:** 2xs(4) xs(8) sm(12) md(16) lg(24) xl(32) 2xl(48) 3xl(64)

## Layout
- **Approach:** Hybrid — grid-disciplined for the viewer (it's a tool), creative for the landing page (it's a pitch)
- **Grid:** Viewer uses CSS grid for panels (1/2/3/4 columns based on active panels). Landing uses flexbox centering.
- **Max content width:** 1200px (landing), full viewport (viewer)
- **Border radius:**
  - sm: 4px (buttons, inputs, small elements)
  - md: 8px (panels, cards, camera bar, input fields)
  - lg: 12px (mockup frames, large containers)
  - full: 9999px (play button, circular elements)
- **Panel grid gap:** 4px (tight, to feel like a continuous viewing surface)

## Motion
- **Approach:** Intentional — aids comprehension, never decorates. No scroll-driven theatrics.
- **Easing:**
  - Enter: ease-out (element appearing)
  - Exit: ease-in (element leaving)
  - Move: ease-in-out (element repositioning)
- **Duration:**
  - Micro: 50-100ms (button hover, toggle state)
  - Short: 150ms (panel transition, focus ring, camera bar toggle)
  - Medium: 250ms (skeleton entrance, panel resize)
  - Long: 500ms (page transition, processing reveal)
- **Key animations:**
  - Skeleton reveal: hold first-frame pose for 1 second, then begin playback (dramatic pause)
  - Speed badge: pulse brightness each loop iteration
  - Processing spinner: dual-ring counter-rotation (2s/1.5s)
  - Processing dots: three cyan dots with staggered pulse (0.3s offset)
  - Panel visibility: fade in/out (not mount/unmount — preserves WebGL contexts)

## Component Patterns
- **Camera angle bar:** Horizontal button row. Active = cyan background + glow shadow + dark text. Inactive = transparent + gray text. Separated from detail layers (Hands/Footwork) by a 1px vertical divider.
- **Panel labels:** Uppercase, 12px Geist Mono, semi-transparent surface background pill, top-left corner of each panel.
- **Timeline:** Fixed bottom bar. Play button (cyan circle), time display (Geist Mono), speed badge (Geist Mono + border), difficulty heatmap (gradient bar at 30% opacity behind scrubber), beat markers (thin vertical lines), cyan playhead with glow.
- **Error states:** Left-border accent (3px), tinted background (10% opacity of the semantic color), matching text color.
- **Empty states:** Icon + descriptive message + primary action. Never just "No items found."
- **Loading states:** Named processing steps ("Extracting poses...") + step counter ("Step 2 of 5") + segmented progress bar.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-18 | Initial design system created | Created by /design-consultation based on competitive research (Steezy, Choreographic, Vicon, FORMI) and product context |
| 2026-03-18 | Clash Grotesk for display | Nobody in this space uses it — sharp, geometric, gives Stepwise a recognizable typographic voice |
| 2026-03-18 | Instrument Sans over Inter for body | Inter is overused. Instrument Sans is equally readable but slightly warmer and more distinctive |
| 2026-03-18 | Geist Mono for data/technical readouts | Reinforces the motion-capture-lab aesthetic. Makes timestamps and speed badges feel like a HUD |
| 2026-03-18 | Single accent color (cyan) only | Restrained palette — when cyan appears, it means "interactive" or "skeleton." No competing accents |
| 2026-03-18 | No hero explainer section | The ghost mode demo IS the explanation. Subtraction default — if it doesn't earn its pixels, cut it |
| 2026-03-18 | Dark mode only for v1 | Every visualization tool uses dark. Cyan skeleton pops on dark backgrounds. No light mode needed yet |
