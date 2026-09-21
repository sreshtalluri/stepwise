/** The dev fixtures the viewer can be pointed at. Built by `npm run assets`. */
export const LESSONS: Record<string, { title: string }> = {
  "good-lesson": { title: "Everything worked — one dancer, a full turn" },
  "failure-lesson": { title: "Cropped feet, an occluded arm, and a re-entry" },
  "two-dancers": { title: "Two dancers, with a crossing" },
  "two-dancers-apart": { title: "Two dancers, far apart — switching cuts" },
  // Synthetic travel. This used to say "today's pipeline pins root_trajectory to the
  // origin"; it no longer does (world placement wired on `grounding-wiring`), but
  // these fixtures are still synthetic and still the only ones here with travel in
  // them — they are hand-built by `npm run assets`, not pipeline output, and nobody
  // has yet checked in a real placed clip to replace them. Titled accordingly.
  travelling: { title: "Synthetic travel — a dancer crossing the floor" },
  "travelling-no-floor": { title: "Synthetic travel, no floor — the usual case" },
};
