# apps/web — lesson viewer (W5)

The 3D lesson viewer. Reads `MotionResult v1` from `packages/motion-contract` and
renders it beside the source video.

## Running it

```bash
npm install
npm run assets   # REQUIRED FIRST — builds the dev GLB/video/JSON into public/fixtures
npm run dev      # http://localhost:3000
npm test         # pure-logic checks in lib/
```

`public/fixtures/` is gitignored: everything in it is derived from the frozen
contract fixtures by `scripts/build-fixture-assets.mjs`. That script needs `ffmpeg`
for the stand-in videos; without it the 3D still works and the videos are skipped.

Three lessons are wired up: `/lesson/good-lesson`, `/lesson/failure-lesson`,
`/lesson/two-dancers`.

## The parts worth knowing

- **The video is the clock.** `requestVideoFrameCallback` → `mixer.setTime(mediaTime)`
  (`components/LessonViewer.tsx`). Nothing is driven by a wall-clock timer.
- **Seeking is a lookup in `sample_times_s`**, never `index / fps_nominal`
  (`lib/motion.ts` `sampleIndexAt`).
- **The body is split into region meshes** sharing one skeleton (`lib/regions.ts`),
  because hiding a bone does not hide a skinned surface. The real MHR export has to
  keep this split — see OPEN-DECISIONS E3.
- **The contact shadow is a real shadow from a world-fixed light**, so it swings as
  you orbit. That is the signature affordance (DESIGN.md §9), not decoration.

## Not in this package

The count strip, parts list, part editing and count anchoring are W6. The marketing
site, upload, processing screen and reveal orbit are W7. The A-B loop here is
time-based; snapping its edges to count boundaries belongs with the count strip.
