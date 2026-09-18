/**
 * Drawable body regions — the single source of truth shared by the GLB exporter
 * (scripts/build-fixture-assets.mjs) and the viewer.
 *
 * Why regions exist at all (OPEN-DECISIONS.md E3): hiding a bone does NOT hide the
 * skinned surface attached to it. To render a limb as `uncertain` or `absent` the
 * surface has to be separately drawable. So the body ships as one shared skeleton
 * plus N region meshes named `region_<id>`, and the real MHR export must do the same.
 *
 * `bone` is the contract joint name whose transform places the region — and whose
 * visibility (together with its ancestors') the region inherits. `tip` is only
 * geometry: the joint the region reaches toward.
 */
export interface BodyRegion {
  id: string;
  /** Contract joint name (joint_hierarchy.joints[].name). */
  bone: string;
  /** Contract joint name the region reaches toward, or null for a blob (head). */
  tip: string | null;
  radius: number;
  /** Plain-language name, used in "left foot not in frame" (DESIGN.md §4, §11). */
  label: string;
}

export const REGIONS: BodyRegion[] = [
  { id: "torso_lower", bone: "pelvis", tip: "spine2", radius: 0.125, label: "hips" },
  { id: "torso_upper", bone: "spine2", tip: "neck", radius: 0.115, label: "torso" },
  { id: "neck", bone: "neck", tip: "head", radius: 0.045, label: "neck" },
  { id: "head", bone: "head", tip: null, radius: 0.105, label: "head" },
  { id: "collar_l", bone: "left_collar", tip: "left_shoulder", radius: 0.06, label: "left shoulder" },
  { id: "collar_r", bone: "right_collar", tip: "right_shoulder", radius: 0.06, label: "right shoulder" },
  { id: "upperarm_l", bone: "left_shoulder", tip: "left_elbow", radius: 0.052, label: "left upper arm" },
  { id: "upperarm_r", bone: "right_shoulder", tip: "right_elbow", radius: 0.052, label: "right upper arm" },
  { id: "forearm_l", bone: "left_elbow", tip: "left_wrist", radius: 0.044, label: "left forearm" },
  { id: "forearm_r", bone: "right_elbow", tip: "right_wrist", radius: 0.044, label: "right forearm" },
  { id: "hand_l", bone: "left_wrist", tip: "left_hand", radius: 0.042, label: "left hand" },
  { id: "hand_r", bone: "right_wrist", tip: "right_hand", radius: 0.042, label: "right hand" },
  { id: "thigh_l", bone: "left_hip", tip: "left_knee", radius: 0.075, label: "left thigh" },
  { id: "thigh_r", bone: "right_hip", tip: "right_knee", radius: 0.075, label: "right thigh" },
  { id: "shin_l", bone: "left_knee", tip: "left_ankle", radius: 0.058, label: "left shin" },
  { id: "shin_r", bone: "right_knee", tip: "right_ankle", radius: 0.058, label: "right shin" },
  { id: "foot_l", bone: "left_ankle", tip: "left_foot", radius: 0.05, label: "left foot" },
  { id: "foot_r", bone: "right_ankle", tip: "right_foot", radius: 0.05, label: "right foot" },
];

/** Joints the "hands" close-up preset frames on. */
export const HAND_JOINTS = ["left_wrist", "right_wrist", "left_hand", "right_hand"];
/** Joints the "feet" close-up preset frames on. */
export const FOOT_JOINTS = ["left_ankle", "right_ankle", "left_foot", "right_foot"];
