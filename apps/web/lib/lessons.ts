/** The dev fixtures the viewer can be pointed at. Built by `npm run assets`. */
export const LESSONS: Record<string, { title: string }> = {
  "good-lesson": { title: "Everything worked — one dancer, a full turn" },
  "failure-lesson": { title: "Cropped feet, an occluded arm, and a re-entry" },
  "two-dancers": { title: "Two dancers, with a crossing" },
  "two-dancers-apart": { title: "Two dancers, far apart — switching cuts" },
  // Synthetic travel. Today's pipeline pins root_trajectory to the origin
  // (OPEN-DECISIONS E6), so these are the only fixtures a follow camera has anything
  // to follow in. Titled so nobody mistakes them for pipeline output.
  travelling: { title: "Synthetic travel — a dancer crossing the floor" },
  "travelling-no-floor": { title: "Synthetic travel, no floor — the usual case" },
};
