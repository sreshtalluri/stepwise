// This file generates the sample-result.json fixture
// Run with: npx ts-node lib/generate-fixture.ts

import type {
  StepwiseResult,
  PoseFrame,
  JointName,
  Joint,
  HandState,
  FootState,
  Beat,
  DifficultySegment,
} from "./types";

function joint(x: number, y: number, z: number, confidence = 0.95): Joint {
  return { x, y, z, confidence };
}

const handStates: HandState[] = ["fist", "open", "spread", "pointing"];
const footStates: FootState[] = ["flat", "heel", "toe", "slide", "airborne"];

export function generateSampleResult(): StepwiseResult {
  const fps = 30;
  const frameCount = 30;
  const duration = frameCount / fps; // 1 second

  const frames: PoseFrame[] = [];

  for (let i = 0; i < frameCount; i++) {
    const t = i / frameCount;
    const timestamp = i / fps;

    // Arm raising: arms go from sides to above head
    const armAngle = t * Math.PI; // 0 to PI
    const armY = 1.4 + Math.sin(armAngle) * 0.4;
    const armX = 0.3 - Math.sin(armAngle) * 0.15;

    const joints: Record<JointName, Joint> = {
      // Head
      nose: joint(0, 1.7, 0.05),
      head: joint(0, 1.75, 0),
      left_eye: joint(-0.03, 1.72, 0.04),
      right_eye: joint(0.03, 1.72, 0.04),
      left_ear: joint(-0.06, 1.7, 0),
      right_ear: joint(0.06, 1.7, 0),
      // Torso
      neck: joint(0, 1.6, 0),
      spine: joint(0, 1.3, 0),
      pelvis: joint(0, 1.0, 0),
      // Left arm (raising)
      left_shoulder: joint(-0.2, 1.5, 0),
      left_elbow: joint(-armX, armY - 0.15, 0),
      left_wrist: joint(-armX - 0.05, armY, 0),
      left_hand: joint(-armX - 0.07, armY + 0.05, 0),
      // Right arm (raising)
      right_shoulder: joint(0.2, 1.5, 0),
      right_elbow: joint(armX, armY - 0.15, 0),
      right_wrist: joint(armX + 0.05, armY, 0),
      right_hand: joint(armX + 0.07, armY + 0.05, 0),
      // Left leg
      left_hip: joint(-0.1, 1.0, 0),
      left_knee: joint(-0.1, 0.55, 0),
      left_ankle: joint(-0.1, 0.1, 0),
      left_foot: joint(-0.1, 0.02, 0.05),
      // Right leg
      right_hip: joint(0.1, 1.0, 0),
      right_knee: joint(0.1, 0.55, 0),
      right_ankle: joint(0.1, 0.1, 0),
      right_foot: joint(0.1, 0.02, 0.05),
    };

    frames.push({
      timestamp,
      joints,
      hands: [
        {
          joint: "left_hand",
          state: handStates[i % handStates.length],
        },
        {
          joint: "right_hand",
          state: handStates[(i + 2) % handStates.length],
        },
      ],
      feet: [
        {
          joint: "left_foot",
          state: footStates[i % footStates.length],
        },
        {
          joint: "right_foot",
          state: footStates[(i + 1) % footStates.length],
        },
      ],
    });
  }

  // Beats every 500ms
  const beats: Beat[] = [
    { timestamp: 0, strength: 1.0 },
    { timestamp: 0.5, strength: 0.7 },
  ];

  // Difficulty segments
  const difficulty: DifficultySegment[] = [
    { start: 0, end: 0.33, score: 0.2 },
    { start: 0.33, end: 0.66, score: 0.5 },
    { start: 0.66, end: 1.0, score: 0.85 },
  ];

  return {
    version: "1.0.0",
    source_url: "https://www.youtube.com/watch?v=example",
    duration,
    fps,
    frames,
    beats,
    difficulty,
    metadata: {
      title: "Sample Arm Raise",
      creator: "Stepwise Demo",
      platform: "youtube",
    },
  };
}

// Export generated data for direct use
export const sampleResult = generateSampleResult();
