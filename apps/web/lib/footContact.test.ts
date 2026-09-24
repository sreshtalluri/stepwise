import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { footContact, jointWorldPosition } from "./footContact";
import type { MotionResult } from "./motion";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fixtures");
const load = (name: string): MotionResult => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf-8"));

test("footContact: planted on the floor, lifted when raised, unknown with no floor", () => {
  const doc = load("good-lesson");
  const names = doc.joint_hierarchy.joints.map((j) => j.name);
  // FK lands the root exactly on root_trajectory.
  const root = doc.joint_hierarchy.root_joint_index;
  assert.deepEqual(jointWorldPosition(doc, 0, 0, root), doc.persons[0].root_trajectory[0].position);

  // Put the floor through the lower of the two ankles: that foot is planted.
  const ankle = (side: string) => jointWorldPosition(doc, 0, 0, names.indexOf(`${side}_ankle`));
  const low = Math.min(ankle("left")[1], ankle("right")[1]);
  doc.grounding = { status: "grounded", floor_plane: { normal: [0, 1, 0], point: [0, low, 0] } };
  const c = footContact(doc, 0, 0);
  assert.ok(c.left === "planted" || c.right === "planted", JSON.stringify(c));

  // Drop the floor half a metre: both feet are off it.
  doc.grounding = { status: "grounded", floor_plane: { normal: [0, 1, 0], point: [0, low - 0.5, 0] } };
  assert.deepEqual(footContact(doc, 0, 0), { left: "lifted", right: "lifted" });

  // No floor fit is no claim at all.
  assert.deepEqual(footContact(load("failure-lesson"), 0, 0), { left: "unknown", right: "unknown" });
});
