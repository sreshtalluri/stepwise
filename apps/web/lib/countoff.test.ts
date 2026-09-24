import { test } from "node:test";
import assert from "node:assert/strict";

import { STATE_POSES, statePoseAt, type StatePose } from "./countoff";

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
