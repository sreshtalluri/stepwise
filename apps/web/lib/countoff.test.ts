import { test } from "node:test";
import assert from "node:assert/strict";

import { COUNT_POSES, STATE_POSES, statePoseAt, type Pt, type StatePose } from "./countoff";

const SITTING: StatePose[] = ["sit", "sitback"];
const FLOOR = 196;

test("every state pose is 11 points in the 100 x 200 box, feet on the floor unless sitting", () => {
  for (const [name, [a, b, seconds]] of Object.entries(STATE_POSES) as [StatePose, (typeof STATE_POSES)[StatePose]][]) {
    assert.ok(seconds > 0, `${name}: glide time`);
    for (const [label, pose] of [["A", a], ["B", b]] as const) {
      assert.equal(pose.length, 11, `${name} ${label}: 11 points`);
      for (const [x, y] of pose) {
        assert.ok(x >= 0 && x <= 100 && y >= 0 && y <= 200, `${name} ${label}: (${x}, ${y}) outside the box`);
      }
      if (SITTING.includes(name)) continue;
      // lFoot and rFoot, standing on the floor like the eight counts (y 194).
      for (const j of [8, 10]) assert.ok(Math.abs(pose[j][1] - FLOOR) <= 2, `${name} ${label}: foot ${j} off the floor`);
    }
  }
});

test("the six new state poses are there by name", () => {
  for (const name of ["shrug", "sit", "wave", "breathe", "look", "sitback"]) assert.ok(name in STATE_POSES, name);
});

test("the idle loop starts on keyframe A and turns at B", () => {
  const [a, b, s] = STATE_POSES.wave;
  assert.deepEqual(statePoseAt("wave", 0), a);
  statePoseAt("wave", s).forEach((p, j) => {
    assert.ok(Math.abs(p[0] - b[j][0]) < 1e-9 && Math.abs(p[1] - b[j][1]) < 1e-9);
  });
});

// Degrees between the two segments at a joint: 0 = straight, 90 = an L.
const bend = (a: Pt, b: Pt, c: Pt) => {
  const t = (p: Pt, q: Pt) => Math.atan2(q[1] - p[1], q[0] - p[0]);
  const d = Math.abs(t(a, b) - t(b, c)) * (180 / Math.PI);
  return Math.min(d, 360 - d);
};
// Degrees off horizontal for the line from the shoulder (the neck) to the hand.
const tilt = (from: Pt, to: Pt) => {
  const d = Math.abs(Math.atan2(to[1] - from[1], to[0] - from[0])) * (180 / Math.PI);
  return Math.min(d, 180 - d);
};

test("the eight counts are a dance: 11 points in the box, one foot on the floor, no standing figure", () => {
  assert.equal(COUNT_POSES.length, 8);
  COUNT_POSES.forEach((p, i) => {
    const c = `count ${i + 1}`;
    assert.equal(p.length, 11, `${c}: 11 points`);
    for (const [x, y] of p) assert.ok(x >= 0 && x <= 100 && y >= 0 && y <= 200, `${c}: (${x}, ${y}) outside the box`);
    const [, neck, pelvis, lE, lH, rE, rH, lK, lF, rK, rF] = p;
    // No jumps: the lower foot is on the floor.
    assert.ok(Math.abs(Math.max(lF[1], rF[1]) - FLOOR) <= 2, `${c}: off the floor`);
    // Bent knees: at least one clearly, and not both straight.
    const knees = [bend(pelvis, lK, lF), bend(pelvis, rK, rF)];
    assert.ok(Math.max(...knees) >= 15, `${c}: no knee bent (${knees})`);
    // No T-pose: never both arms out level with both legs straight.
    const flat = [lH, rH].every((h) => tilt(neck, h) < 20);
    assert.ok(!(flat && knees.every((k) => k < 10)), `${c}: T-pose`);
    // Weight off centre: the pelvis is off the feet's midpoint, or the torso leans.
    const lean = tilt(pelvis, neck);
    assert.ok(Math.abs(pelvis[0] - (lF[0] + rF[0]) / 2) >= 3 || lean <= 85, `${c}: standing square`);
    // Asymmetric arms: the hands are not mirror images across the spine.
    const mirror = Math.hypot(lH[0] - 50 + (rH[0] - 50), lH[1] - rH[1]) + Math.hypot(lE[0] - 50 + (rE[0] - 50), lE[1] - rE[1]);
    assert.ok(mirror >= 15, `${c}: arms mirror each other`);
  });
});

test("counts 1 and 5 are the hits: the biggest change of shape into them", () => {
  const move = (a: Pt[], b: Pt[]) => a.reduce((s, p, j) => s + Math.hypot(p[0] - b[j][0], p[1] - b[j][1]), 0);
  const into = COUNT_POSES.map((p, i) => move(COUNT_POSES[(i + 7) % 8], p));
  const top2 = [...into.keys()].sort((a, b) => into[b] - into[a]).slice(0, 2).sort();
  assert.deepEqual(top2, [0, 4], `moves into each count: ${into.map(Math.round)}`);
});
