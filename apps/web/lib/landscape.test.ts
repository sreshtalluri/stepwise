/**
 * The aspect-dependent math, for clips that are not 9:16: the overlay's letterbox, the
 * video crop-follow, the picker stills and the close-up squares, on the 16:9
 * `landscape-lesson` fixture and on 4:3 and square frames.
 *
 * Run: npm test   (requires `npm run assets` first — it reads the built fixtures)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  containFit,
  cropTransform,
  projectToFrame,
  sourceAspect,
  sourceProjection,
  steadyCropTrack,
  CROP_TARGET_HEIGHT,
  MAX_CROP_ZOOM,
  type MotionResult,
} from "./motion";
import { dancerBox, firstWellObserved, markerPoint, sideWord, stillCrop } from "./dancers";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));
const land = load("landscape-lesson");
const tall = load("good-lesson");
const near = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;

test("the landscape fixture is 16:9 and the aspect comes from the intrinsics", () => {
  assert.equal(land.source_video.width_px, 1280);
  assert.equal(land.source_video.height_px, 720);
  assert.ok(near(sourceAspect(land), 16 / 9));
  assert.ok(near(sourceAspect(tall), 9 / 16));
});

test("containFit: which axis letterboxes, for wide and tall frames in wide and tall panels", () => {
  // 16:9 in a portrait phone panel: all the width, a third of the height.
  const a = containFit(16 / 9, 390, 690);
  assert.equal(a.x, 1);
  assert.ok(near(a.y, (390 / 690) / (16 / 9)));
  // 16:9 in a panel of its own shape: no bars.
  assert.deepEqual(containFit(16 / 9, 1280, 720), { x: 1, y: 1 });
  // 9:16 in a wide desktop panel: the old case, bars left and right.
  const b = containFit(9 / 16, 900, 700);
  assert.equal(b.y, 1);
  assert.ok(near(b.x, (9 / 16) / (900 / 700)));
  // 4:3 and square in a 16:9 panel: pillarboxed.
  assert.ok(near(containFit(4 / 3, 1600, 900).x, 0.75));
  assert.ok(near(containFit(1, 1600, 900).x, 900 / 1600));
  // Nothing measured yet: no letterbox assumed.
  assert.deepEqual(containFit(16 / 9, 0, 0), { x: 1, y: 1 });
});

test("overlay: a 16:9 frame's world point lands on the letterboxed pixel in portrait and landscape panels", () => {
  const { reference_width_px: W, reference_height_px: H } = land.camera.intrinsics;
  const m = land.camera.camera_to_world;
  for (const k of [0, 1]) {
    const p = land.persons[k].root_trajectory[0].position as [number, number, number];
    const d = [p[0] - m[12], p[1] - m[13], p[2] - m[14]];
    const c = [0, 4, 8].map((j) => m[j] * d[0] + m[j + 1] * d[1] + m[j + 2] * d[2]);
    const uv = projectToFrame(land, p)!;
    assert.ok(uv.x > 0 && uv.x < W && uv.y > 0 && uv.y < H, "the dancer is in the wide frame");
    // Portrait phone panel, a panel of the clip's own shape, a very wide one.
    for (const [elW, elH] of [[390, 690], [1280, 720], [1400, 500]]) {
      const P = sourceProjection(land, elW, elH);
      const w = P[12] * c[0] + P[13] * c[1] + P[14] * c[2] + P[15];
      const x = (((P[0] * c[0] + P[1] * c[1] + P[2] * c[2] + P[3]) / w + 1) / 2) * elW;
      const y = ((1 - (P[4] * c[0] + P[5] * c[1] + P[6] * c[2] + P[7]) / w) / 2) * elH;
      // The same contain box DancerMarkers and the crop use.
      const fit = containFit(sourceAspect(land), elW, elH);
      const fw = elW * fit.x, fh = elH * fit.y;
      assert.ok(near(x, (elW - fw) / 2 + (uv.x / W) * fw, 1e-6), `x at ${elW}x${elH}`);
      assert.ok(near(y, (elH - fh) / 2 + (uv.y / H) * fh, 1e-6), `y at ${elW}x${elH}`);
    }
  }
});

test("crop-follow: a frame that fills its panel behaves exactly as before", () => {
  const body = { x: 0.55, y: 0.3, width: 0.12, height: 0.36 };
  assert.deepEqual(cropTransform(body, { x: 1, y: 1 }), cropTransform(body));
});

test("crop-follow: a 16:9 clip in a portrait panel zooms past the letterbox into real pixels, never beyond the frame", () => {
  const fit = containFit(16 / 9, 390, 690);
  // A dancer half the frame tall, left of centre: the panel is filled by the frame's height.
  const body = { x: 0.2, y: 0.3, width: 0.1, height: 0.5 };
  const w = cropTransform(body, fit);
  assert.ok(near(w.zoom * fit.y * body.height, CROP_TARGET_HEIGHT), `framed to the target height: ${w.zoom}`);
  assert.ok(w.zoom * fit.y >= 1, "the frame now covers the panel's height: no bars left");
  // Element fraction of the dancer's centre after `translate(t) scale(zoom)`.
  const at = (p: number, k: number, t: number) => 0.5 + w.zoom * k * (p - 0.5) + t;
  assert.ok(near(at(0.25, fit.x, w.tx), 0.5), "centred across");
  // Rule 2 on both axes: the frame still covers the panel edge to edge.
  for (const [k, t] of [[fit.x, w.tx], [fit.y, w.ty]]) {
    assert.ok(at(0, k, t) <= 1e-9 && at(1, k, t) >= 1 - 1e-9, `no black past the frame: ${k} ${t}`);
  }
  // A dancer at the very edge is not re-centred.
  const edge = cropTransform({ x: 0, y: 0.3, width: 0.08, height: 0.5 }, fit);
  assert.ok(near(0.5 + edge.zoom * fit.x * (0 - 0.5) + edge.tx, 0), "window stops at the frame's left edge");
  // A tiny dancer: capped against the panel's height, not the letterboxed frame's.
  assert.ok(near(cropTransform({ x: 0.5, y: 0.5, width: 0.01, height: 0.02 }, fit).zoom, MAX_CROP_ZOOM / fit.y));
});

test("crop-follow: a narrower-than-panel frame may slide toward the dancer but never out of the panel", () => {
  const fit = containFit(9 / 16, 900, 700);
  const w = cropTransform({ x: 0.0, y: 0.35, width: 0.1, height: 0.5 }, fit);
  const left = 0.5 + w.zoom * fit.x * -0.5 + w.tx;
  const right = 0.5 + w.zoom * fit.x * 0.5 + w.tx;
  assert.ok(w.zoom * fit.x < 1, "still narrower than the panel");
  assert.ok(left >= -1e-9 && right <= 1 + 1e-9, `frame inside the panel: ${left} ${right}`);
});

test("picker stills: 3:4 in pixels and inside the frame, on 16:9, 4:3 and square clips", () => {
  for (const [vw, vh] of [[1280, 720], [1920, 1080], [1440, 1080], [1080, 1080]]) {
    for (const box of [
      { x: 0.45, y: 0.2, width: 0.08, height: 0.6 }, // a standing dancer in a wide shot
      { x: 0.9, y: 0.1, width: 0.1, height: 0.9 }, // at the right edge, full height
      { x: 0, y: 0, width: 1, height: 1 },
      null,
    ]) {
      const r = stillCrop(box, vw, vh);
      assert.ok(near((r.width * vw) / (r.height * vh), 0.75, 1e-9), `3:4 at ${vw}x${vh}: ${JSON.stringify(r)}`);
      assert.ok(r.x >= -1e-9 && r.y >= -1e-9 && r.x + r.width <= 1 + 1e-9 && r.y + r.height <= 1 + 1e-9, "inside");
      if (box && box.height < 1) assert.ok(r.height * vh >= box.height * vh - 1e-6, "tall enough for the dancer");
    }
  }
});

test("landscape fixture: the two dancers are told apart by side and their markers sit over them", () => {
  const boxes = land.persons.map((_, k) => dancerBox(land, k, firstWellObserved(land, k))!);
  assert.equal(sideWord(boxes[0]), "left");
  assert.equal(sideWord(boxes[1]), "right");
  land.persons.forEach((_, k) => {
    const i = firstWellObserved(land, k);
    const m = markerPoint(land, k, i)!;
    assert.ok(m.x > boxes[k].x && m.x < boxes[k].x + boxes[k].width, `marker ${k} over its dancer`);
  });
  // A dancer in a wide shot is a narrow box: the 3:4 still is cropped from the width.
  const r = stillCrop(boxes[0], 1280, 720);
  assert.ok(r.width < 0.5, `a slice of the frame, not all of it: ${r.width}`);
});

test("close-ups on a 16:9 clip are square in pixels and follow their own dancer's side", () => {
  const W = land.source_video.width_px, H = land.source_video.height_px;
  const cx = [0, 1].map((k) => {
    const track = steadyCropTrack(land, k, "hands").filter((r) => r !== null);
    assert.ok(track.length > 0);
    for (const r of track) {
      assert.ok(near(r!.width * W, r!.height * H, 1e-6), "square in pixels");
      assert.ok(r!.x >= -1e-9 && r!.x + r!.width <= 1 + 1e-9, "inside the frame");
    }
    return track.reduce((s, r) => s + r!.x + r!.width / 2, 0) / track.length;
  });
  assert.ok(cx[0] < 0.5 && cx[1] > 0.5, `left dancer's hands on the left: ${cx}`);
});
