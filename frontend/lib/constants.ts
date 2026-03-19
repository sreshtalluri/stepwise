// Design tokens
export const colors = {
  bg: "#0a0a0a",
  surface: "#141414",
  border: "#222222",
  textPrimary: "#f0f0f0",
  textSecondary: "#888888",
  accent: "#00d4ff",
  accentGlow: "rgba(0, 212, 255, 0.2)",
  error: "#ff4444",
  success: "#44ff88",
  heatmapLow: "#44ff88",
  heatmapMid: "#ffdd44",
  heatmapHigh: "#ff4444",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  base: 16,
  lg: 24,
  xl: 32,
  "2xl": 48,
  "3xl": 64,
} as const;

// Skeleton joint connections (bone topology)
export const BONE_CONNECTIONS: [string, string][] = [
  // Spine
  ["pelvis", "spine"],
  ["spine", "neck"],
  ["neck", "head"],
  ["head", "nose"],
  // Left arm
  ["neck", "left_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["left_wrist", "left_hand"],
  // Right arm
  ["neck", "right_shoulder"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["right_wrist", "right_hand"],
  // Left leg
  ["pelvis", "left_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["left_ankle", "left_foot"],
  // Right leg
  ["pelvis", "right_hip"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
  ["right_ankle", "right_foot"],
];

// Foot state colors
export const FOOT_COLORS: Record<string, string> = {
  flat: "#44ff88",
  heel: "#ffdd44",
  toe: "#ff8844",
  slide: "#4488ff",
};

// Processing steps
export const PROCESSING_STEPS = [
  "Downloading video...",
  "Extracting poses...",
  "Detecting hands...",
  "Detecting beats...",
  "Almost ready...",
];

// Speed ramp config
export const SPEED_RAMP = {
  initialSpeed: 0.5,
  increment: 0.1,
  maxSpeed: 1.5,
};

export const POLL_INTERVAL = 2500;
