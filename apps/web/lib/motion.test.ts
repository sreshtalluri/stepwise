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
  regionVisibility,
  absentNotes,
  defaultPersonIndex,
  scoreDancers,
  dancerColor,
  projectToFrame,
  viewLabel,
  followStep,
  damp,
  deadzoneFor,
  travelExtent,
  travelsMeaningfully,
  projectBoxToFrame,
  cropTransform,
  MAX_CROP_ZOOM,
  CROP_TARGET_HEIGHT,
  FOLLOW,
  BODY_HEIGHT_M,
  type Vec3,
  type MotionResult,
} from "./motion";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));

const good = load("good-lesson");
const failure = load("failure-lesson");
const two = load("two-dancers");
const travelling = load("travelling");

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

test("only the camera preset may call itself camera evidence", () => {
  assert.equal(viewLabel("camera", false), "camera · camera view");
  assert.equal(viewLabel("side", false), "side · estimated view");
  assert.equal(viewLabel("front", false), "front · estimated view");
  assert.equal(viewLabel("top", true), "top · mirrored · estimated view");
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
