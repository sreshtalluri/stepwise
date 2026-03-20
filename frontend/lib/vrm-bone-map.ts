/**
 * Maps SMPL body_pose joint indices to VRM humanoid bone names.
 *
 * SMPL body_pose has 21 joints (indices 0-20), excluding the root (pelvis).
 * The root orientation comes from global_orient instead.
 *
 * VRM humanoid bones follow the VRM specification:
 * https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md
 *
 * Joint indices reference the SMPL body model joint ordering.
 * null means the SMPL joint has no direct VRM equivalent.
 */
export const SMPL_TO_VRM_BONE_MAP: Record<number, string | null> = {
  0: "hips",              // SMPL: pelvis (body_pose root, not global_orient)
  1: "leftUpperLeg",      // SMPL: left_hip
  2: "rightUpperLeg",     // SMPL: right_hip
  3: "spine",             // SMPL: spine1
  4: "leftLowerLeg",      // SMPL: left_knee
  5: "rightLowerLeg",     // SMPL: right_knee
  6: "chest",             // SMPL: spine2
  7: "leftFoot",          // SMPL: left_ankle
  8: "rightFoot",         // SMPL: right_ankle
  9: "upperChest",        // SMPL: spine3
  10: "leftToes",         // SMPL: left_foot
  11: "rightToes",        // SMPL: right_foot
  12: "neck",             // SMPL: neck
  13: "leftShoulder",     // SMPL: left_collar
  14: "rightShoulder",    // SMPL: right_collar
  15: "head",             // SMPL: head
  16: "leftUpperArm",     // SMPL: left_shoulder
  17: "rightUpperArm",    // SMPL: right_shoulder
  18: "leftLowerArm",     // SMPL: left_elbow
  19: "rightLowerArm",    // SMPL: right_elbow
  20: null,               // SMPL: left_wrist -> VRM leftHand (handled separately via hand_pose)
};

/**
 * VRM bone name for the root (driven by global_orient, not body_pose).
 */
export const VRM_ROOT_BONE = "hips";

/**
 * Hand bone mapping for SMPL-X hand_pose.
 *
 * SMPL-X has 15 joints per hand x 3 axis-angle values = 45 floats per hand.
 * VRM has 15 finger bones per hand (3 per finger x 5 fingers).
 */
export const SMPL_HAND_TO_VRM: Record<number, string> = {
  // Left hand: indices 0-14 in left_hand_pose
  // Index finger
  0: "leftIndexProximal",
  1: "leftIndexIntermediate",
  2: "leftIndexDistal",
  // Middle finger
  3: "leftMiddleProximal",
  4: "leftMiddleIntermediate",
  5: "leftMiddleDistal",
  // Pinky
  6: "leftLittleProximal",
  7: "leftLittleIntermediate",
  8: "leftLittleDistal",
  // Ring finger
  9: "leftRingProximal",
  10: "leftRingIntermediate",
  11: "leftRingDistal",
  // Thumb
  12: "leftThumbMetacarpal",
  13: "leftThumbProximal",
  14: "leftThumbDistal",
};

/**
 * Right hand uses the same indices but with "right" prefix.
 */
export function getRightHandBoneName(leftBoneName: string): string {
  return leftBoneName.replace("left", "right");
}
