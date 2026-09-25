import type { MotionResult } from "./motion";
import { lookupJoint } from "./regions";

/**
 * Per-foot "is it on the floor" from the 3D, for a diagram or a weight-shift cue.
 *
 * WHY ONLY PLANTED/LIFTED. Measured on a real 33 s solo (solo-02, 488 samples) against
 * the video: whole-foot-off-the-floor frames read correctly (6/6 spot-checked), but
 * flat vs on-the-toes vs on-the-heel did not (about half of "toe" frames were flat in
 * the video) — the floor fit is ~4 cm noisy (ball height p5 = -4 cm) and the foot
 * itself only articulates ~11 deg p95 over a clip, which is inside that noise. So the
 * finer split is not offered: a diagram showing "relevé" on a flat foot is exactly the
 * confident-wrong-output failure DESIGN.md §7h forbids.
 *
 * Hand shape (fist / open / point) is deliberately NOT here: MHR's fingers never leave a
 * semi-curled band (per-finger curl 55-114 deg over the same clip; open is ~0, a fist
 * ~250), so any classifier over them returns the same answer every frame. See
 * services/motion-api/vendor/fast-sam-3d-body/tools/hand_crops.py.
 */
export type FootContact = "planted" | "lifted" | "unknown";

/**
 * Height above the floor plane, metres, above which the foot counts as lifted. BOTH
 * points must clear it. The ankle joint sits ~6 cm up on a flat foot (solo-02 median
 * 5.7 cm), so its threshold is that plus the ball's. Calibration knobs, not physics.
 */
export const FOOT_LIFT_M = { ankle: 0.09, ball: 0.06 };

type V3 = [number, number, number];
type Q = readonly number[]; // [x, y, z, w]

export function qmul(a: Q, b: Q): [number, number, number, number] {
  const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
  return [
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
    aw * bw - ax * bx - ay * by - az * bz,
  ];
}

export function qrot(q: Q, v: readonly number[]): V3 {
  const [x, y, z, w] = q;
  // v + 2w(q×v) + 2 q×(q×v)
  const tx = 2 * (y * v[2] - z * v[1]), ty = 2 * (z * v[0] - x * v[2]), tz = 2 * (x * v[1] - y * v[0]);
  return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)];
}

/**
 * World position of one joint at one sample: forward kinematics over the contract's
 * `rest_translation` and `rest_rotation * rotation` (joint_hierarchy.rotation_convention),
 * rooted at `root_trajectory`. Rest bone lengths — the contract carries no per-frame scale.
 */
export function jointWorldPosition(doc: MotionResult, personIndex: number, sampleIndex: number, jointIndex: number): V3 {
  const joints = doc.joint_hierarchy.joints;
  const person = doc.persons[personIndex];
  const rootIdx = doc.joint_hierarchy.root_joint_index;
  const chain: number[] = [];
  for (let j = jointIndex; j >= 0 && j !== rootIdx; j = joints[j].parent_index) chain.unshift(j);
  if (chain.length && joints[chain[0]].parent_index !== rootIdx) throw new Error(`joint ${jointIndex} is not below the root`);
  const root = person.root_trajectory[sampleIndex];
  let rot: Q = root.rotation;
  let pos: V3 = [...root.position] as V3;
  for (const j of chain) {
    const d = qrot(rot, joints[j].rest_translation);
    pos = [pos[0] + d[0], pos[1] + d[1], pos[2] + d[2]];
    rot = qmul(rot, qmul(joints[j].rest_rotation, person.samples[sampleIndex].joints[j].rotation));
  }
  return pos;
}

/** Planted/lifted per foot at one sample; "unknown" with no floor or an absent foot. */
export function footContact(doc: MotionResult, personIndex: number, sampleIndex: number): { left: FootContact; right: FootContact } {
  const floor = doc.grounding.status === "grounded" ? doc.grounding.floor_plane : null;
  const byName = new Map(doc.joint_hierarchy.joints.map((j) => [j.name, j.index]));
  const joints = doc.persons[personIndex]?.samples[sampleIndex]?.joints;
  const one = (side: "left" | "right"): FootContact => {
    const ankle = lookupJoint(byName, `${side}_ankle`);
    const ball = lookupJoint(byName, `${side}_foot`);
    if (!floor || !joints || ankle === undefined || ball === undefined) return "unknown";
    if (joints[ankle].visibility === "absent" || joints[ball].visibility === "absent") return "unknown";
    const n = floor.normal, p0 = floor.point;
    const height = (j: number) => {
      const p = jointWorldPosition(doc, personIndex, sampleIndex, j);
      return (p[0] - p0[0]) * n[0] + (p[1] - p0[1]) * n[1] + (p[2] - p0[2]) * n[2];
    };
    return height(ankle) > FOOT_LIFT_M.ankle && height(ball) > FOOT_LIFT_M.ball ? "lifted" : "planted";
  };
  return { left: one("left"), right: one("right") };
}
