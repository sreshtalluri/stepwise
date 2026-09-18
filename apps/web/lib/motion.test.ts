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
  type MotionResult,
} from "./motion";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));

const good = load("good-lesson");
const failure = load("failure-lesson");
const two = load("two-dancers");

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
