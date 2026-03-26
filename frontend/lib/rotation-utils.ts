/**
 * Convert axis-angle rotation (3 values) to quaternion (4 values).
 *
 * SMPL body_pose contains 21 joints x 3 axis-angle values = 63 floats.
 * VRM bones expect quaternion rotations. This converts between them.
 *
 * axis-angle: [ax, ay, az] where magnitude = rotation angle in radians,
 * direction = rotation axis.
 */

export function axisAngleToQuaternion(
  ax: number,
  ay: number,
  az: number
): [number, number, number, number] {
  const angle = Math.sqrt(ax * ax + ay * ay + az * az);
  if (angle < 1e-8) {
    return [0, 0, 0, 1]; // identity quaternion
  }
  const halfAngle = angle / 2;
  const s = Math.sin(halfAngle) / angle;
  return [ax * s, ay * s, az * s, Math.cos(halfAngle)]; // [x, y, z, w]
}

/**
 * Get the number of body joints based on body_pose array length.
 * SMPL: 69 values = 23 joints x 3
 * SMPL-X: 63 values = 21 joints x 3
 */
export function getBodyJointCount(bodyPose: number[]): number {
  return Math.floor(bodyPose.length / 3);
}

/**
 * Extract a single joint's axis-angle rotation from the body_pose array.
 *
 * body_pose is 63 or 69 floats (SMPL-X: 21 joints, SMPL: 23 joints),
 * each with 3 axis-angle values. Joint index i starts at body_pose[i * 3].
 */
export function getJointRotation(
  bodyPose: number[],
  jointIndex: number
): [number, number, number, number] {
  const offset = jointIndex * 3;
  return axisAngleToQuaternion(
    bodyPose[offset],
    bodyPose[offset + 1],
    bodyPose[offset + 2]
  );
}
