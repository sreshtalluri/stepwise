/**
 * The one runnable check for the non-trivial viewer logic: seeking by
 * sample_times_s, conservative region visibility, and default-dancer selection.
 *
 * Run: npm test   (requires `npm run assets` first — it reads the built fixtures)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  sampleIndexAt,
  cropRectAt,
  cropRegions,
  steadyCropTrack,
  steadyCropAt,
  regionVisibility,
  absentNotes,
  defaultPersonIndex,
  scoreDancers,
  dancerColor,
  projectToFrame,
  sourceProjection,
  viewLabel,
  followStep,
  damp,
  deadzoneFor,
  travelExtent,
  travelsMeaningfully,
  rootPlacementObserved,
  rootPositionAt,
  soleLift,
  projectBoxToFrame,
  cropTransform,
  MAX_CROP_ZOOM,
  CROP_TARGET_HEIGHT,
  FOLLOW,
  BODY_HEIGHT_M,
  type FollowTuning,
  type Vec3,
  type MotionResult,
} from "./motion";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));

const good = load("good-lesson");
const failure = load("failure-lesson");
const two = load("two-dancers");
const travelling = load("travelling");
const unplaced = load("unplaced-dancer");

test("sampleIndexAt is a step function on sample_times_s, not index/fps arithmetic", () => {
  const t = good.sample_times_s;
  assert.equal(sampleIndexAt(t, -1), 0);
  assert.equal(sampleIndexAt(t, 0), 0);
  assert.equal(sampleIndexAt(t, 1e9), t.length - 1);
  // Exactly on a sample, and just before the next one: both resolve to that sample.
  for (const i of [1, 42, 128, t.length - 1]) {
    assert.equal(sampleIndexAt(t, t[i]), i, `exact hit at ${i}`);
    assert.equal(sampleIndexAt(t, t[i] - 1e-9), i - 1 < 0 ? 0 : i - 1, `just before ${i}`);
  }
  // Never rounds up to a sample that has not happened yet.
  for (let i = 0; i < t.length - 1; i++) {
    const mid = (t[i] + t[i + 1]) / 2;
    assert.equal(sampleIndexAt(t, mid), i);
  }
});

test("cropRectAt is a step function on crop_rects.*, and null means not localized (DESIGN.md §7h)", () => {
  // good-lesson has a rect at every sample — a real one comes back untouched.
  const idx = 5;
  assert.deepEqual(
    cropRectAt(good, 0, "hands", good.sample_times_s[idx]),
    good.persons[0].crop_rects.hands[idx],
  );

  // failure-lesson's feet are null for most of the clip (LessonViewer.tsx's own
  // comment cites 8/90) — find one null sample and one real one.
  const feet = failure.persons[0].crop_rects.feet;
  const times = failure.sample_times_s;
  const nullIdx = feet.findIndex((r) => r === null);
  const realIdx = feet.findIndex((r) => r !== null);
  assert.ok(nullIdx >= 0 && realIdx >= 0, "fixture must contain both a null and a real foot crop");
  assert.equal(cropRectAt(failure, 0, "feet", times[nullIdx]), null);
  assert.deepEqual(cropRectAt(failure, 0, "feet", times[realIdx]), feet[realIdx]);

  // Step function, not interpolation: halfway between two samples resolves to
  // whichever one sampleIndexAt would pick, never a blended rectangle.
  const mid = (times[nullIdx] + times[nullIdx + 1]) / 2;
  assert.deepEqual(cropRectAt(failure, 0, "feet", mid), feet[sampleIndexAt(times, mid)]);

  // An out-of-range person index is absent, not a crash.
  assert.equal(cropRectAt(failure, 99, "feet", 0), null);
});

test("steadyCropTrack: one zoom for the clip, smoothed centre, nulls stay null and are never averaged across", () => {
  const W = 1000, H = 1000;
  const n = 60;
  const times = Array.from({ length: n }, (_, i) => i / 15);
  // Jittery rects: size alternates 100/300 px, centre zig-zags +-40 px; a null gap at 30..32.
  const rects = times.map((_, i) => {
    if (i >= 30 && i <= 32) return null;
    const s = i % 2 ? 300 : 100;
    const cx = 500 + (i % 2 ? 40 : -40);
    return { x: (cx - s / 2) / W, y: (500 - s / 2) / H, width: s / W, height: s / H };
  });
  const doc = {
    sample_times_s: times,
    source_video: { width_px: W, height_px: H },
    persons: [{ crop_rects: { hands: rects, feet: rects } }],
  } as unknown as MotionResult;

  const track = steadyCropTrack(doc, 0, "hands");
  assert.equal(track.length, n);
  for (let i = 30; i <= 32; i++) assert.equal(track[i], null);
  const real = track.filter((r) => r !== null);
  // One size: the p90 side, 300 px.
  for (const r of real) assert.ok(Math.abs(r!.width * W - 300) < 1e-9 && Math.abs(r!.height * H - 300) < 1e-9);
  // The +-40 px zig-zag averages out in the middle of a run.
  const cx = (r: NonNullable<(typeof track)[number]>) => (r.x + r.width / 2) * W;
  assert.ok(Math.abs(cx(track[15]!) - 500) < 5, `centre ${cx(track[15]!)}`);
  // Interpolates between two real samples, steps (no blending) next to the gap.
  const mid = steadyCropAt(times, track, (times[10] + times[11]) / 2)!;
  assert.ok(Math.abs(cx(mid) - (cx(track[10]!) + cx(track[11]!)) / 2) < 1e-9);
  assert.deepEqual(steadyCropAt(times, track, (times[29] + times[30]) / 2), track[29]);
  assert.equal(steadyCropAt(times, track, times[31]), null);
});

test("cropRegions: per-side insets when the lesson has them, combined for older lessons", () => {
  assert.deepEqual(cropRegions(good, 0, false), ["hands", "feet"]);
  const doc = structuredClone(good);
  const nulls = doc.sample_times_s.map(() => null);
  Object.assign(doc.persons[0].crop_rects, { left_hand: nulls, right_hand: nulls, left_foot: nulls, right_foot: nulls });
  // Dancer facing camera: their right hand is on screen-left; mirroring swaps it.
  assert.deepEqual(cropRegions(doc, 0, false), ["right_hand", "left_hand", "right_foot", "left_foot"]);
  assert.deepEqual(cropRegions(doc, 0, true), ["left_hand", "right_hand", "left_foot", "right_foot"]);
  assert.deepEqual(cropRegions(doc, 9, false), ["hands", "feet"]);
  // A per-side track steadies on its own, like any other region.
  assert.equal(steadyCropTrack(doc, 0, "left_hand").every((r) => r === null), true);
});

test("failure fixture: feet go absent, left arm goes uncertain, and the shin stays drawn", () => {
  const before = regionVisibility(failure, 0, 0);
  assert.equal(before.get("foot_l"), "observed");
  assert.equal(before.get("forearm_l"), "observed");

  const cropped = regionVisibility(failure, 0, 40); // inside both failure windows
  assert.equal(cropped.get("foot_l"), "absent");
  assert.equal(cropped.get("foot_r"), "absent");
  // Suppression propagates down the chain, never up: the knee was seen, so the shin
  // is still drawn even though the ankle below it left the frame.
  assert.equal(cropped.get("shin_l"), "observed");
  assert.equal(cropped.get("thigh_l"), "observed");
  // A low-confidence shoulder suppresses the whole arm below it, including the hand.
  assert.equal(cropped.get("upperarm_l"), "uncertain");
  assert.equal(cropped.get("forearm_l"), "uncertain");
  assert.equal(cropped.get("hand_l"), "uncertain");
  assert.equal(cropped.get("upperarm_r"), "observed");

  assert.deepEqual(absentNotes(cropped).sort(), ["left foot not in frame", "right foot not in frame"]);

  // Re-entry after the dropout: sample 51 is clean again (fixtures README).
  assert.equal(regionVisibility(failure, 0, 51).get("forearm_l"), "observed");
});

test("good fixture: a dancer turned away is still fully observed (DESIGN.md §7h case 1)", () => {
  const midTurn = sampleIndexAt(good.sample_times_s, 7.0);
  const vis = regionVisibility(good, 0, midTurn);
  assert.equal([...vis.values()].every((v) => v === "observed"), true);
  assert.deepEqual(absentNotes(vis), []);
});

test("default dancer = best coverage, centre distance breaks the tie", () => {
  assert.equal(defaultPersonIndex(good), 0);

  const scores = scoreDancers(two);
  assert.equal(scores.length, 2);
  // Both dancers are offset symmetrically and share a coverage-collapsing crossing,
  // so the scores must be close but the function must still return a single winner.
  assert.ok(Math.abs(scores[0].score - scores[1].score) < 0.05);
  assert.ok(scores.every((s) => s.coverage > 0.8 && s.centreDistance >= 0));
  assert.ok([0, 1].includes(defaultPersonIndex(two)));

  // Only the selected dancer is saturated; the other is a muted neutral.
  const sel = defaultPersonIndex(two);
  const other = sel === 0 ? 1 : 0;
  assert.notEqual(dancerColor(two, sel, sel), dancerColor(two, other, sel));
  assert.equal(dancerColor(two, other, sel), "#6E675F");
  // Single-dancer clip with a sampled accent uses the clip's own colour.
  assert.equal(dancerColor(good, 0, 0), good.accent_color.hex);
});

test("projectToFrame puts the dancer inside the frame and rejects points behind the camera", () => {
  const uv = projectToFrame(good, good.persons[0].root_trajectory[0].position as [number, number, number])!;
  assert.ok(uv.x > 0 && uv.x < good.source_video.width_px, `x ${uv.x}`);
  assert.ok(uv.y > 0 && uv.y < good.source_video.height_px, `y ${uv.y}`);
  // Camera sits at z = +3.2 looking down -Z; something further along +Z is behind it.
  assert.equal(projectToFrame(good, [0, 1, 20]), null);
});

test("sourceProjection lands a world point on the element pixel projectToFrame names", () => {
  // Overlay contract: the canvas over a contain-fitted <video> must agree with the
  // source camera, letterbox included. Both a wider and a taller element than the frame.
  // Plus an off-centre principal point, which a centred fixture would never exercise.
  const i0 = good.camera.intrinsics;
  const offCentre = { ...good, camera: { ...good.camera, intrinsics: { ...i0, cx: i0.cx * 0.8, cy: i0.cy * 1.1 } } };
  const p = good.persons[0].root_trajectory[0].position as [number, number, number];
  const { reference_width_px: W, reference_height_px: H } = i0;
  const m = good.camera.camera_to_world; // world -> camera, as projectToFrame does it
  const d = [p[0] - m[12], p[1] - m[13], p[2] - m[14]];
  const c = [0, 4, 8].map((k) => m[k] * d[0] + m[k + 1] * d[1] + m[k + 2] * d[2]);
  for (const doc of [good, offCentre]) for (const [elW, elH] of [[900, 300], [300, 900]]) {
    const uv = projectToFrame(doc, p)!;
    const P = sourceProjection(doc, elW, elH);
    const w = P[12] * c[0] + P[13] * c[1] + P[14] * c[2] + P[15];
    const x = ((P[0] * c[0] + P[1] * c[1] + P[2] * c[2] + P[3]) / w + 1) / 2 * elW;
    const y = (1 - (P[4] * c[0] + P[5] * c[1] + P[6] * c[2] + P[7]) / w) / 2 * elH;
    const s = Math.min(elW / W, elH / H);
    assert.ok(Math.abs(x - ((elW - W * s) / 2 + uv.x * s)) < 1e-6, `x at ${elW}x${elH}`);
    assert.ok(Math.abs(y - ((elH - H * s) / 2 + uv.y * s)) < 1e-6, `y at ${elW}x${elH}`);
  }
});

test("only the camera preset may call itself camera evidence", () => {
  assert.equal(viewLabel("camera", false), "camera · camera view");
  assert.equal(viewLabel("side", false), "side · estimated view");
  assert.equal(viewLabel("front", false), "front · estimated view");
  assert.equal(viewLabel("top", true), "top · mirrored · estimated view");
  assert.equal(viewLabel("overlay", false), "on video · camera view");
});

/* ------------------------------------------------------- world placement */

test("a never-placed track is not offset by a placeholder that is not a place", () => {
  // OPEN-DECISIONS E6 item 4. The short track's position is a character-local
  // constant sitting 2.16 m above the floor; every sample says so by never being
  // `observed`. Reading provenance is the only thing separating it from a real one,
  // since both are just three finite numbers.
  assert.equal(rootPlacementObserved(unplaced, 0), true);
  assert.equal(rootPlacementObserved(unplaced, 1), false);
  assert.equal(rootPlacementObserved(travelling, 0), true);
  assert.equal(rootPlacementObserved(good, 0), true);

  // And the placeholder really would fly: if the gate were dropped the dancer would
  // be lifted more than a metre off the plane the same document fits.
  const floorY = good.grounding.floor_plane!.point[1];
  const placeholder = unplaced.persons[1]!.root_trajectory[0].position[1];
  assert.ok(placeholder - floorY > 1, `the placeholder must be visibly wrong, got ${placeholder - floorY} m`);
});

test("the world position is lerped the way the GLB's LINEAR channels are, not stepped", () => {
  const t = travelling.sample_times_s;
  const rt = travelling.persons[0].root_trajectory;
  // Exactly on a sample: exactly that sample, no drift from the interpolation.
  for (const i of [0, 37, 120, t.length - 1]) {
    assert.deepEqual(rootPositionAt(travelling, 0, t[i]), rt[i].position.slice(0, 3));
  }
  // Half way between two: half way, not either end — the whole point, since a step
  // would hold for a 15 Hz sample while the mixer lerps the pose at display rate.
  const i = 100;
  const mid = rootPositionAt(travelling, 0, (t[i] + t[i + 1]) / 2);
  for (let k = 0; k < 3; k++) {
    assert.ok(
      Math.abs(mid[k] - (rt[i].position[k] + rt[i + 1].position[k]) / 2) < 1e-9,
      `axis ${k}: ${mid[k]}`,
    );
  }
  assert.notDeepEqual(mid, rt[i].position.slice(0, 3));

  // Outside the timeline it holds the end samples rather than extrapolating a
  // position the pipeline never claimed.
  assert.deepEqual(rootPositionAt(travelling, 0, -5), rt[0].position.slice(0, 3));
  assert.deepEqual(rootPositionAt(travelling, 0, 1e6), rt[rt.length - 1].position.slice(0, 3));
});

test("soleLift: planted soles land on the floor, a jump keeps its height, nothing sinks", () => {
  // Sole 4 cm under the floor while planted (the measured solo-02 bias), then a
  // 30 cm jump, then planted again 2 cm under.
  const gaps = [-0.04, -0.04, -0.04, -0.04, 0.3, 0.3, 0.3, -0.02, -0.02, -0.02, -0.02];
  const lift = soleLift(gaps);
  const after = gaps.map((g, k) => g + lift[k]);
  assert.ok(after.every((g) => g >= -1e-12), `under the floor: ${after}`);
  // Planted, away from the take-off/landing edges: exactly on it, not floating.
  for (const k of [0, 1, 2, 8, 9, 10]) assert.ok(Math.abs(after[k]) < 1e-9, `k=${k}: ${after[k]}`);
  // The jump is lifted by the interpolated bias (~3 cm), not flattened onto the floor.
  for (const k of [4, 5, 6]) assert.ok(after[k] > 0.3 && after[k] < 0.35, `k=${k}: ${after[k]}`);
  // No contact at all: only ever lifted, never pulled down.
  assert.deepEqual(soleLift([0.2, 0.3]), [0, 0]);
});

/* --------------------------------------------------------------- follow rig */

test("the follow deadzone makes a pinned trajectory a no-op, and travel still moves the camera", () => {
  // Regime 1, today: root_trajectory is pinned (OPEN-DECISIONS E6). The whole clip's
  // wander has to stay inside the deadzone, or follow would twitch on every clip.
  assert.ok(travelExtent(good, 0) < deadzoneFor(BODY_HEIGHT_M), `good travels ${travelExtent(good, 0)}`);
  assert.equal(travelsMeaningfully(good, 0), false);
  assert.equal(travelsMeaningfully(failure, 0), false);

  // Regime 2: real travel. The synthesised fixture must actually travel, or it proves
  // nothing about the rig.
  assert.ok(travelExtent(travelling, 0) > 2, `travelling travels ${travelExtent(travelling, 0)}`);
  assert.equal(travelsMeaningfully(travelling, 0), true);

  const dz = deadzoneFor(BODY_HEIGHT_M);
  const aim: Vec3 = [0, 1, 0];
  // Inside the deadzone: byte-for-byte no movement, not "a very small movement".
  assert.deepEqual(followStep(aim, [dz * 0.9, 1, 0], dz, 1 / 60), aim);
  // Outside it: the camera moves, but never all the way — it trails.
  const moved = followStep(aim, [3, 1, 0], dz, 1 / 60);
  assert.ok(moved[0] > aim[0] && moved[0] < 3 - dz, `stepped to ${moved[0]}`);
});

test("follow trails by more than the deadzone while travelling — travel never reads as standing still", () => {
  // A dancer walking at a constant 1 m/s for four seconds. If the rig locked on, the
  // dancer would sit dead centre the whole way and be indistinguishable from a dancer
  // standing still (DESIGN.md §7h — the same class of problem as a faked floor).
  const dz = deadzoneFor(BODY_HEIGHT_M);
  let aim: Vec3 = [0, 1, 0];
  let x = 0;
  const dt = 1 / 60;
  for (let i = 0; i < 4 / dt; i++) {
    x += 1 * dt;
    aim = followStep(aim, [x, 1, 0], dz, dt);
  }
  const lag = x - aim[0];
  assert.ok(lag > dz, `lag ${lag} must exceed the deadzone ${dz}`);
  assert.ok(lag < dz + 1, `lag ${lag} must stay bounded — the dancer has to stay on screen`);

  // And it catches up once they stop, so the view re-centres rather than drifting.
  // It settles ON the deadzone edge, approached exponentially, never past it.
  for (let i = 0; i < 4 / dt; i++) aim = followStep(aim, [x, 1, 0], dz, dt);
  assert.ok(Math.abs(x - aim[0]) <= dz + 1e-3, `settled lag ${x - aim[0]}`);
  assert.ok(Math.abs(x - aim[0]) > dz * 0.99, `must not overshoot into the deadzone: ${x - aim[0]}`);
});

test("the follow lag is capped, so a real sprint cannot leave the dancer off the panel", () => {
  // solo-01's measured worst case: 4.42 m/s sustained over a second. Without the cap
  // the steady-state trail is deadzone + v*tau = 2.34 m, and the body preset frames
  // from 3.57 m with a 0.93 m horizontal half-frame on a phone — the dancer is not
  // off-centre, they are gone.
  const dz = deadzoneFor(BODY_HEIGHT_M);
  const dt = 1 / 60;
  let aim: Vec3 = [0, 1, 0];
  let x = 0;
  for (let i = 0; i < 2 / dt; i++) {
    x += 4.42 * dt;
    aim = followStep(aim, [x, 1, 0], dz, dt);
  }
  const lag = x - aim[0];
  assert.ok(lag <= dz * FOLLOW.maxLagFactor + 1e-9, `lag ${lag} must not exceed the cap ${dz * FOLLOW.maxLagFactor}`);
  assert.ok(lag > dz, `lag ${lag} must still exceed the deadzone — travel must still read`);

  // The cap is a ceiling, not a lock: below it nothing changes, so the deadzone
  // behaviour and the slow-walk easing are reached exactly as they were tuned.
  const slow = followStep([0, 1, 0], [dz * 0.9, 1, 0], dz, dt);
  assert.deepEqual(slow, [0, 1, 0]);
  const capped: FollowTuning = { ...FOLLOW, maxLagFactor: 1e6 };
  assert.deepEqual(followStep([0, 1, 0], [dz + 0.01, 1, 0], dz, dt), followStep([0, 1, 0], [dz + 0.01, 1, 0], dz, dt, capped));
});

test("damp is frame-rate independent", () => {
  // Same elapsed time, different step sizes, same answer. A naive
  // `current += (target - current) * k` does NOT have this property, and the camera
  // would follow at a different speed on a 120 Hz phone than on a 60 Hz laptop.
  const one = damp(0, 1, 0.5, 1);
  let many = 0;
  for (let i = 0; i < 100; i++) many = damp(many, 1, 0.5, 0.01);
  assert.ok(Math.abs(one - many) < 1e-9, `${one} vs ${many}`);
  assert.equal(damp(5, 5, 0.5, 1), 5);
});

test("the deadzone scales with what is framed, so close-ups are not swallowed by it", () => {
  const body = deadzoneFor(BODY_HEIGHT_M);
  const hands = deadzoneFor(0.35);
  assert.ok(hands < body / 4, `hands ${hands} vs body ${body}`);
  assert.ok(hands >= FOLLOW.minDeadzone);
  assert.equal(deadzoneFor(0), FOLLOW.minDeadzone);
});

/* --------------------------------------------------------- video crop-follow */

test("the body crop is projected from the same world bounds the 3D pane frames", () => {
  // A dancer-sized box around the fixture's root position, projected through the
  // clip's own camera, must land inside the frame and cover a plausible fraction of it.
  const root = good.persons[0].root_trajectory[0].position as Vec3;
  const box = projectBoxToFrame(good, [root[0] - 0.4, 0, root[2] - 0.3], [root[0] + 0.4, 1.85, root[2] + 0.3])!;
  assert.ok(box, "a dancer in front of the camera must project");
  assert.ok(box.x > 0 && box.y > 0 && box.x + box.width < 1 && box.y + box.height < 1, JSON.stringify(box));
  assert.ok(box.height > 0.2 && box.height < 0.95, `height ${box.height}`);
  // Straddling the camera plane is not projectable, and must say so rather than
  // return a rectangle that looks fine and is nonsense.
  assert.equal(projectBoxToFrame(good, [-1, 0, -1], [1, 2, 20]), null);
});

test("crop-follow never claims the dancer filled a frame they did not (DESIGN.md §7h)", () => {
  // 1. Never zooms out. There are no pixels outside the shot to zoom out into.
  assert.equal(cropTransform({ x: 0, y: 0, width: 1, height: 1 }).zoom, 1);
  assert.equal(cropTransform({ x: 0.1, y: 0.1, width: 0.8, height: 0.9 }).zoom, 1);

  // 2. Never magnifies past the cap, however small the dancer got — a blurry crop
  //    implies detail the source never had.
  assert.equal(cropTransform({ x: 0.48, y: 0.48, width: 0.02, height: 0.02 }).zoom, MAX_CROP_ZOOM);

  // 3. A small-but-followable dancer is framed to the target height.
  const small = cropTransform({ x: 0.4, y: 0.4, width: 0.1, height: 0.36 });
  assert.ok(Math.abs(small.zoom - CROP_TARGET_HEIGHT / 0.36) < 1e-9);

  // 4. The window stops at the edge of the shot: a dancer in the corner is NOT
  //    re-centred, because re-centring would have to pad with frame nobody filmed.
  //    They slide off centre instead, which is the truth.
  const corner = cropTransform({ x: 0.0, y: 0.0, width: 0.1, height: 0.3 });
  const centred = cropTransform({ x: 0.45, y: 0.35, width: 0.1, height: 0.3 });
  assert.equal(corner.zoom, centred.zoom, "clamping must not change the magnification");
  assert.ok(Math.abs(centred.tx) < 0.02 && Math.abs(centred.ty) < 0.02, JSON.stringify(centred));
  const half = 0.5 / corner.zoom;
  // The pan is capped at exactly "window half-extent from the frame edge".
  assert.ok(Math.abs(corner.tx) <= corner.zoom * (0.5 - half) + 1e-9, `tx ${corner.tx}`);
  assert.ok(Math.abs(corner.ty) <= corner.zoom * (0.5 - half) + 1e-9, `ty ${corner.ty}`);

  // 5. A dancer partly outside the frame is reported, not silently cropped around.
  assert.equal(cropTransform({ x: -0.05, y: 0.2, width: 0.2, height: 0.5 }).clipped, true);
  assert.equal(cropTransform({ x: 0.2, y: 0.2, width: 0.2, height: 0.5 }).clipped, false);
  assert.equal(cropTransform(null).zoom, 1);
});

test("crop pan puts the dancer at the panel centre when the frame allows it", () => {
  // The transform contract: `translate(tx, ty) scale(zoom)` maps frame point p to
  // zoom * (p - 0.5) + t. Check the dancer's centre really lands on 0.
  const body = { x: 0.55, y: 0.3, width: 0.12, height: 0.36 };
  const w = cropTransform(body);
  assert.ok(Math.abs(w.zoom * (body.x + body.width / 2 - 0.5) + w.tx) < 1e-9, "x centred");
  assert.ok(Math.abs(w.zoom * (body.y + body.height / 2 - 0.5) + w.ty) < 1e-9, "y centred");
});

test("a real (MHR, 127-joint) document resolves every region, not just the fixtures", async () => {
  const { MHR_ALIASES, REGIONS, HAND_JOINTS, FOOT_JOINTS } = await import("./regions");
  const here = path.dirname(fileURLToPath(import.meta.url));
  const mhr = JSON.parse(readFileSync(path.join(here, "../test/mhr-joints.json"), "utf8"));
  const names = new Set(mhr.joints.map((j: { name: string }) => j.name));
  for (const canonical of [...REGIONS.flatMap((r) => [r.bone, r.tip]), ...HAND_JOINTS, ...FOOT_JOINTS]) {
    if (canonical) assert.ok(names.has(MHR_ALIASES[canonical]), `${canonical} -> ${MHR_ALIASES[canonical]} is not an MHR joint`);
  }
  // Before the aliases, exactly this rendered an empty stage: all observed, all "absent".
  const doc = {
    joint_hierarchy: mhr,
    persons: [{ samples: [{ joints: mhr.joints.map(() => ({ visibility: "observed" })) }] }],
  } as unknown as MotionResult;
  assert.deepEqual(absentNotes(regionVisibility(doc, 0, 0)), []);
});
