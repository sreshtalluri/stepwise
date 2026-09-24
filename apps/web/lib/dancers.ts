/**
 * Telling dancers apart from THIS clip's own pixels: the "Who are you learning?"
 * picker's thumbnails and the numbered markers over the video. Pure, tested in
 * dancers.test.ts.
 *
 * Both come from the contract's joints pushed through the clip's own camera
 * (`jointWorldPosition` + `projectToFrameNorm`), so a thumbnail shows exactly the
 * person whose mesh takes that colour. A dancer the pipeline never placed
 * (`rootPlacementObserved` false) has no position in the frame to project, so their
 * thumbnail falls back to the hand/foot crop rects, and they get no marker — a
 * number floating in the wrong place is worse than none.
 */
import { jointWorldPosition } from "./footContact";
import { lookupJoint } from "./regions";
import { projectToFrameNorm, rootPlacementObserved, type MotionResult, type Rect } from "./motion";

/** A sample counts as well observed once this share of the dancer's joints were seen. */
export const WELL_OBSERVED = 0.8;

function observedShare(doc: MotionResult, personIndex: number, sampleIndex: number): number {
  const joints = doc.persons[personIndex].samples[sampleIndex]?.joints ?? [];
  if (!joints.length) return 0;
  return joints.filter((j) => j.visibility === "observed").length / joints.length;
}

/** First sample where the dancer is well observed; else their best-observed one. */
export function firstWellObserved(doc: MotionResult, personIndex: number): number {
  let best = 0;
  let bestShare = -1;
  for (let i = 0; i < doc.sample_times_s.length; i++) {
    const s = observedShare(doc, personIndex, i);
    if (s >= WELL_OBSERVED) return i;
    if (s > bestShare) [best, bestShare] = [i, s];
  }
  return best;
}

const clampRect = (r: Rect): Rect => {
  const x0 = Math.max(0, r.x), y0 = Math.max(0, r.y);
  const x1 = Math.min(1, r.x + r.width), y1 = Math.min(1, r.y + r.height);
  return { x: x0, y: y0, width: Math.max(0, x1 - x0), height: Math.max(0, y1 - y0) };
};

/**
 * The dancer's box in [0,1] frame space at one sample, padded, clamped to the frame.
 * Projected joints when the dancer was placed, else the union of their hand and foot
 * crop rects stretched upward to a body, else null (the caller shows the whole frame).
 */
export function dancerBox(doc: MotionResult, personIndex: number, sampleIndex: number): Rect | null {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const grow = (x: number, y: number) => {
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  };
  if (rootPlacementObserved(doc, personIndex)) {
    for (let j = 0; j < doc.joint_hierarchy.joints.length; j++) {
      let p: [number, number, number];
      try {
        p = jointWorldPosition(doc, personIndex, sampleIndex, j);
      } catch {
        continue; // a joint outside the root's subtree
      }
      const uv = projectToFrameNorm(doc, p);
      if (uv) grow(uv.x, uv.y);
    }
  }
  if (!(x1 > x0)) {
    const rects = doc.persons[personIndex].crop_rects;
    for (const r of [rects.hands?.[sampleIndex], rects.feet?.[sampleIndex]]) {
      if (r) { grow(r.x, r.y); grow(r.x + r.width, r.y + r.height); }
    }
    if (!(x1 > x0)) return null;
    // Hands and feet miss the head; a standing body is ~1.2x the hands-to-feet span.
    y0 = Math.max(0, y1 - (y1 - y0) * 1.25);
  }
  const padX = (x1 - x0) * 0.15 + 0.02, padY = (y1 - y0) * 0.1 + 0.02;
  return clampRect({ x: x0 - padX, y: y0 - padY, width: x1 - x0 + 2 * padX, height: y1 - y0 + 2 * padY });
}

/** "left" / "middle" / "right" of the frame, for the picker's second line. */
export function sideWord(box: Rect | null): "left" | "middle" | "right" | null {
  if (!box) return null;
  const cx = box.x + box.width / 2;
  return cx < 0.4 ? "left" : cx > 0.6 ? "right" : "middle";
}

/**
 * Where to pin a dancer's number on the frame: just above the head, in [0,1] frame
 * space. Null for an unplaced dancer, a missing head joint, or a point behind the camera.
 */
export function markerPoint(doc: MotionResult, personIndex: number, sampleIndex: number): { x: number; y: number } | null {
  if (!rootPlacementObserved(doc, personIndex)) return null;
  const byName = new Map(doc.joint_hierarchy.joints.map((j) => [j.name, j.index]));
  const head = lookupJoint(byName, "head");
  if (head === undefined) return null;
  let p: [number, number, number];
  try {
    p = jointWorldPosition(doc, personIndex, sampleIndex, head);
  } catch {
    return null;
  }
  const up = doc.grounding.status === "none" ? [0, 1, 0] : doc.grounding.floor_plane?.normal ?? [0, 1, 0];
  return projectToFrameNorm(doc, [p[0] + up[0] * 0.28, p[1] + up[1] * 0.28, p[2] + up[2] * 0.28]);
}
