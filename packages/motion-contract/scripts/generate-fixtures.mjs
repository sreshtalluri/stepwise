#!/usr/bin/env node
// One-off generator for fixtures/*.json. NOT part of the contract — the committed
// JSON is the fixture; this script exists only so the motion data is a smooth,
// physically-plausible dance loop instead of hand-typed noise. Re-run and hand-edit
// the output if a scenario needs to change. Run: node scripts/generate-fixtures.mjs
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const round = (x, dp = 5) => Math.round(x * 10 ** dp) / 10 ** dp;
const vec3 = (x, y, z) => [round(x), round(y), round(z)];

function axisAngleQuat(axis, angleRad) {
  const [ax, ay, az] = axis;
  const norm = Math.hypot(ax, ay, az) || 1;
  const s = Math.sin(angleRad / 2);
  return [round(ax / norm * s), round(ay / norm * s), round(az / norm * s), round(Math.cos(angleRad / 2))];
}
const IDENTITY_Q = [0, 0, 0, 1];

// Standard body skeleton, 24 joints, no fingers/toes (3D hand articulation is out
// of v1 scope per PRD §5). glb_node_name deliberately differs in casing/naming
// convention from the canonical joint `name` to demonstrate the mapping is by
// name, not by array position.
const JOINTS = [
  { name: "pelvis", parent: -1, glb: "Hips", t: [0, 0, 0] },
  { name: "left_hip", parent: 0, glb: "LeftUpLeg", t: [0.09, -0.06, 0] },
  { name: "right_hip", parent: 0, glb: "RightUpLeg", t: [-0.09, -0.06, 0] },
  { name: "spine1", parent: 0, glb: "Spine", t: [0, 0.12, 0] },
  { name: "left_knee", parent: 1, glb: "LeftLeg", t: [0, -0.42, 0.02] },
  { name: "right_knee", parent: 2, glb: "RightLeg", t: [0, -0.42, 0.02] },
  { name: "spine2", parent: 3, glb: "Spine1", t: [0, 0.12, 0] },
  { name: "left_ankle", parent: 4, glb: "LeftFoot", t: [0, -0.42, -0.02] },
  { name: "right_ankle", parent: 5, glb: "RightFoot", t: [0, -0.42, -0.02] },
  { name: "spine3", parent: 6, glb: "Spine2", t: [0, 0.12, 0] },
  { name: "left_foot", parent: 7, glb: "LeftToeBase", t: [0, -0.08, 0.12] },
  { name: "right_foot", parent: 8, glb: "RightToeBase", t: [0, -0.08, 0.12] },
  { name: "neck", parent: 9, glb: "Neck", t: [0, 0.18, 0] },
  { name: "left_collar", parent: 9, glb: "LeftShoulder", t: [0.08, 0.1, 0] },
  { name: "right_collar", parent: 9, glb: "RightShoulder", t: [-0.08, 0.1, 0] },
  { name: "head", parent: 12, glb: "Head", t: [0, 0.12, 0] },
  { name: "left_shoulder", parent: 13, glb: "LeftArm", t: [0.12, 0, 0] },
  { name: "right_shoulder", parent: 14, glb: "RightArm", t: [-0.12, 0, 0] },
  { name: "left_elbow", parent: 16, glb: "LeftForeArm", t: [0.28, 0, 0] },
  { name: "right_elbow", parent: 17, glb: "RightForeArm", t: [-0.28, 0, 0] },
  { name: "left_wrist", parent: 18, glb: "LeftHand", t: [0.26, 0, 0] },
  { name: "right_wrist", parent: 19, glb: "RightHand", t: [-0.26, 0, 0] },
  { name: "left_hand", parent: 20, glb: "LeftHandTip", t: [0.08, 0, 0] },
  { name: "right_hand", parent: 21, glb: "RightHandTip", t: [-0.08, 0, 0] },
];

function jointHierarchy() {
  return {
    rotation_convention: "local-to-parent quaternion, relative to MHR rest (A-pose), glTF component order [x,y,z,w]",
    root_joint_index: 0,
    joints: JOINTS.map((j, i) => ({
      name: j.name,
      index: i,
      parent_index: j.parent,
      glb_node_name: j.glb,
      rest_rotation: IDENTITY_Q,
      rest_translation: vec3(...j.t),
    })),
  };
}

const byName = Object.fromEntries(JOINTS.map((j, i) => [j.name, i]));

// One "dance cycle" of local rotation per joint, in radians, by name. Legs and
// arms swing contralaterally like a natural step; spine/head bounce on the beat.
function poseAngle(name, t, freq) {
  const w = 2 * Math.PI * freq;
  switch (name) {
    case "left_hip": return { axis: [1, 0, 0], angle: 0.35 * Math.sin(w * t) };
    case "right_hip": return { axis: [1, 0, 0], angle: 0.35 * Math.sin(w * t + Math.PI) };
    case "left_knee": return { axis: [1, 0, 0], angle: 0.15 + 0.35 * Math.max(0, Math.sin(w * t + Math.PI / 4)) };
    case "right_knee": return { axis: [1, 0, 0], angle: 0.15 + 0.35 * Math.max(0, Math.sin(w * t + Math.PI / 4 + Math.PI)) };
    case "left_ankle": return { axis: [1, 0, 0], angle: 0.2 * Math.sin(w * t + Math.PI / 2) };
    case "right_ankle": return { axis: [1, 0, 0], angle: 0.2 * Math.sin(w * t + Math.PI / 2 + Math.PI) };
    case "left_shoulder": return { axis: [1, 0, 0], angle: 0.55 * Math.sin(w * t + Math.PI) };
    case "right_shoulder": return { axis: [1, 0, 0], angle: 0.55 * Math.sin(w * t) };
    case "left_elbow": return { axis: [1, 0, 0], angle: 0.3 + 0.25 * Math.sin(w * t + Math.PI + 0.4) };
    case "right_elbow": return { axis: [1, 0, 0], angle: 0.3 + 0.25 * Math.sin(w * t + 0.4) };
    case "spine1": return { axis: [0, 0, 1], angle: 0.04 * Math.sin(w * t * 0.5) };
    case "spine2": return { axis: [0, 0, 1], angle: 0.03 * Math.sin(w * t * 0.5 + 0.3) };
    case "spine3": return { axis: [1, 0, 0], angle: 0.03 * Math.sin(w * t * 2) };
    case "neck": return { axis: [1, 0, 0], angle: 0.06 * Math.sin(w * t * 2 + 0.5) };
    case "head": return { axis: [1, 0, 0], angle: 0.05 * Math.sin(w * t * 2 + 0.8) };
    default: return { axis: [1, 0, 0], angle: 0 };
  }
}

function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

const observedProvenance = () => ({ observed: true, interpolated: false, suppressed: null });

function makeGoodLesson() {
  const fps = 15;
  const durationS = 14.0;
  const n = Math.round(durationS * fps); // 210
  const sampleTimesS = Array.from({ length: n }, (_, i) => round(i / fps, 6));
  const freq = 30 / durationS / 2; // ~1.07 Hz — roughly one full step every 2 of the 30 counts

  const joints = jointHierarchy();

  const rootTrajectory = sampleTimesS.map((t) => {
    // A full turn during the middle of the clip — this is the honesty-boundary
    // showcase (DESIGN.md §7h case 1): tracked continuously through a turn away
    // from camera and back, never dropping to "absent" while doing so.
    const turnProgress = smoothstep(0.4 * durationS, 0.6 * durationS, t);
    const yaw = turnProgress * 2 * Math.PI + (t > 0.6 * durationS ? 0.08 * Math.sin(2 * Math.PI * freq * t) : 0);
    return {
      position: vec3(0.1 * Math.sin(2 * Math.PI * freq * 0.25 * t), 0.95 + 0.03 * Math.sin(2 * Math.PI * freq * 2 * t), 0.05 * Math.cos(2 * Math.PI * freq * 0.25 * t)),
      rotation: axisAngleQuat([0, 1, 0], yaw),
      provenance: observedProvenance(),
    };
  });

  const samples = sampleTimesS.map((t) => ({
    joints: JOINTS.map((j) => {
      const { axis, angle } = poseAngle(j.name, t, freq);
      return {
        rotation: axisAngleQuat(axis, angle),
        provenance: observedProvenance(),
        visibility: "observed",
      };
    }),
  }));

  const handsCrop = sampleTimesS.map((t) => ({
    x: round(0.38 + 0.08 * Math.sin(2 * Math.PI * freq * t), 4),
    y: round(0.3 + 0.03 * Math.sin(2 * Math.PI * freq * 2 * t), 4),
    width: 0.28,
    height: 0.18,
  }));
  const feetCrop = sampleTimesS.map((t) => ({
    x: round(0.36 + 0.06 * Math.sin(2 * Math.PI * freq * t + Math.PI), 4),
    y: 0.8,
    width: 0.32,
    height: 0.16,
  }));

  return {
    schema_version: "1.0.0",
    job_id: "job_9f3a2e7c4b1d4a6e8f0a1b2c3d4e5f60",
    source_video: {
      asset_id: "asset_video_7a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d",
      width_px: 1080,
      height_px: 1920,
      rotation_deg: 0,
      duration_s: durationS,
      fps_nominal: fps,
      audio_offset_s: 0.02,
    },
    sample_times_s: sampleTimesS,
    camera: {
      model: "pinhole",
      intrinsics: { fx: 1450, fy: 1450, cx: 540, cy: 960, reference_width_px: 1080, reference_height_px: 1920 },
      camera_to_world: [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 1.4, 3.2, 1,
      ],
    },
    grounding: {
      status: "grounded",
      floor_plane: { normal: [0, 1, 0], point: [0, 0, 0] },
    },
    accent_color: { hex: "#D9A441", source: "sampled" },
    joint_hierarchy: joints,
    animation: { clip_id: "lesson_full", glb_asset_id: "asset_glb_1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d" },
    persons: [
      {
        person_id: "person_1",
        track_id: 1,
        shape_params: { vector: [0.12, -0.05, 0.03, 0.0, 0.08, -0.02, 0.0, 0.01, -0.01, 0.0], source: "well_observed_frames" },
        root_trajectory: rootTrajectory,
        samples,
        crop_rects: { hands: handsCrop, feet: feetCrop },
      },
    ],
    model_report: {
      pipeline_git_sha: "808b53c",
      models: [
        { name: "rtmo-m", version: "body7", license: "Apache-2.0", license_flags: [] },
        { name: "bytetrack", version: "upstream-main", license: "MIT", license_flags: [] },
        { name: "sam-3d-body-dinov3", version: "hf:facebook/sam-3d-body-dinov3", license: "SAM License", license_flags: ["itar-military-use-prohibited", "citation-required-for-research-publication"] },
        { name: "mhr", version: "v1.0.1", license: "Apache-2.0", license_flags: ["body-model-asset-license-see-zip"] },
      ],
      measured_performance: { fps: 3.52, peak_vram_mb: 18200, cost_usd: 0.09 },
    },
  };
}

function makeFailureLesson() {
  const fps = 15;
  const durationS = 6.0;
  const n = Math.round(durationS * fps); // 90
  const sampleTimesS = Array.from({ length: n }, (_, i) => round(i / fps, 6));
  const freq = 30 / 14 / 2; // same tempo as the good lesson, shorter excerpt

  const joints = jointHierarchy();
  const leftArmChain = ["left_shoulder", "left_elbow", "left_wrist", "left_hand"];
  const footChain = ["left_ankle", "right_ankle", "left_foot", "right_foot"];

  // Mid-playback dropout + re-entry: the left arm is blocked by another dancer
  // from sample 30 to 50 (2.0s-3.33s). Re-entry at 51 must return to fully
  // observed so a viewer seeking across the gap sees the contract recover cleanly.
  const dropoutStart = 30;
  const dropoutEnd = 50; // inclusive

  const rootTrajectory = sampleTimesS.map((t) => ({
    position: vec3(0.08 * Math.sin(2 * Math.PI * freq * 0.25 * t), 0.95, 0),
    rotation: IDENTITY_Q,
    provenance: observedProvenance(),
  }));

  const samples = sampleTimesS.map((t, i) => ({
    joints: JOINTS.map((j) => {
      const { axis, angle } = poseAngle(j.name, t, freq);
      const rotation = axisAngleQuat(axis, angle);

      if (footChain.includes(j.name)) {
        // Feet cropped out of frame for nearly the whole clip (a handful of
        // samples near the start are still visible before the framing tightens).
        const feetVisible = i < 8;
        return feetVisible
          ? { rotation, provenance: observedProvenance(), visibility: "observed" }
          : { rotation, provenance: { observed: false, interpolated: false, suppressed: "out_of_frame" }, visibility: "absent" };
      }

      if (leftArmChain.includes(j.name) && i >= dropoutStart && i <= dropoutEnd) {
        // The literal "observed AND interpolated AND suppressed at once" case
        // (PRD §6): the estimator still produced a low-confidence value most of
        // these frames (observed=true) which the Kalman chain also smoothed
        // (interpolated=true), and it stays flagged low_confidence because
        // confidence never cleared threshold during the occlusion.
        const stillProducedSomething = i % 4 !== 0; // most frames; a few are fully blocked
        return {
          rotation,
          provenance: { observed: stillProducedSomething, interpolated: true, suppressed: "low_confidence" },
          visibility: "uncertain",
        };
      }

      return { rotation, provenance: observedProvenance(), visibility: "observed" };
    }),
  }));

  const handsCrop = sampleTimesS.map((t, i) =>
    i >= dropoutStart && i <= dropoutEnd
      ? null
      : { x: round(0.4 + 0.06 * Math.sin(2 * Math.PI * freq * t), 4), y: 0.32, width: 0.26, height: 0.17 },
  );
  const feetCrop = sampleTimesS.map((_, i) => (i < 8 ? { x: 0.38, y: 0.8, width: 0.3, height: 0.16 } : null));

  return {
    schema_version: "1.0.0",
    job_id: "job_3c8d1e2f4a5b6c7d8e9f0a1b2c3d4e5f",
    source_video: {
      asset_id: "asset_video_2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e",
      width_px: 1080,
      height_px: 1920,
      rotation_deg: 0,
      duration_s: durationS,
      fps_nominal: fps,
      audio_offset_s: 0.0,
    },
    sample_times_s: sampleTimesS,
    camera: {
      model: "pinhole",
      intrinsics: { fx: 1450, fy: 1450, cx: 540, cy: 960, reference_width_px: 1080, reference_height_px: 1920 },
      camera_to_world: [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 1.4, 3.2, 1,
      ],
    },
    grounding: {
      // Feet were cropped for nearly the whole clip -> no floor fit at all.
      // DESIGN.md §10: never fake a plane.
      status: "none",
      floor_plane: null,
    },
    accent_color: { hex: "#1E7A6F", source: "fallback" },
    joint_hierarchy: joints,
    animation: { clip_id: "lesson_full", glb_asset_id: "asset_glb_9e8d7c6b5a4938271605f4e3d2c1b0a9" },
    persons: [
      {
        person_id: "person_1",
        track_id: 1,
        shape_params: { vector: [0.12, -0.05, 0.03, 0.0, 0.08, -0.02, 0.0, 0.01, -0.01, 0.0], source: "well_observed_frames" },
        root_trajectory: rootTrajectory,
        samples,
        crop_rects: { hands: handsCrop, feet: feetCrop },
      },
    ],
    model_report: {
      pipeline_git_sha: "808b53c",
      models: [
        { name: "rtmo-m", version: "body7", license: "Apache-2.0", license_flags: [] },
        { name: "bytetrack", version: "upstream-main", license: "MIT", license_flags: [] },
        { name: "sam-3d-body-dinov3", version: "hf:facebook/sam-3d-body-dinov3", license: "SAM License", license_flags: ["itar-military-use-prohibited", "citation-required-for-research-publication"] },
        { name: "mhr", version: "v1.0.1", license: "Apache-2.0", license_flags: ["body-model-asset-license-see-zip"] },
      ],
      measured_performance: { fps: 3.31, peak_vram_mb: 17650, cost_usd: 0.03 },
    },
  };
}

writeFileSync(path.join(root, "fixtures", "good-lesson.json"), JSON.stringify(makeGoodLesson(), null, 2) + "\n");
writeFileSync(path.join(root, "fixtures", "failure-lesson.json"), JSON.stringify(makeFailureLesson(), null, 2) + "\n");
console.log("wrote fixtures/good-lesson.json and fixtures/failure-lesson.json");
