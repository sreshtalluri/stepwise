// StepwiseResult TypeScript interface
// Matches the expected schema for pose extraction results

export interface Joint {
  x: number;
  y: number;
  z: number;
  confidence: number;
}

export type JointName =
  | "nose"
  | "left_eye"
  | "right_eye"
  | "left_ear"
  | "right_ear"
  | "left_shoulder"
  | "right_shoulder"
  | "left_elbow"
  | "right_elbow"
  | "left_wrist"
  | "right_wrist"
  | "left_hip"
  | "right_hip"
  | "left_knee"
  | "right_knee"
  | "left_ankle"
  | "right_ankle"
  | "pelvis"
  | "spine"
  | "neck"
  | "head"
  | "left_foot"
  | "right_foot"
  | "left_hand"
  | "right_hand";

export type HandState = "fist" | "open" | "spread" | "pointing";
export type FootState = "flat" | "heel" | "toe" | "slide" | "airborne";

export interface HandAnnotation {
  joint: "left_hand" | "right_hand";
  state: HandState;
}

export interface FootAnnotation {
  joint: "left_foot" | "right_foot";
  state: FootState;
}

export interface PoseFrame {
  timestamp: number;
  joints: Record<JointName, Joint>;
  hands?: HandAnnotation[];
  feet?: FootAnnotation[];
}

export interface Beat {
  timestamp: number;
  strength: number; // 0-1
}

export interface DifficultySegment {
  start: number;
  end: number;
  score: number; // 0-1, 0=easy, 1=hard
}

export interface StepwiseResult {
  version: string;
  source_url: string;
  duration: number; // seconds
  fps: number;
  frames: PoseFrame[];
  beats: Beat[];
  difficulty: DifficultySegment[];
  metadata?: {
    title?: string;
    creator?: string;
    platform?: string;
  };
}

export interface ProcessResponse {
  jobId: string;
}

export interface StatusResponse {
  status: "processing" | "complete" | "error";
  step?: string;
  result_url?: string;
  error_message?: string;
  error?: string;
}

export type CameraAngle = "video" | "front" | "back" | "mirror" | "ghost";
export type DetailLayer = "hands" | "footwork";

export type ViewPreset = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface ViewerState {
  activeAngles: Set<CameraAngle>;
  activeLayers: Set<DetailLayer>;
  currentFrame: number;
  isPlaying: boolean;
  playbackSpeed: number;
  loopStart: number | null;
  loopEnd: number | null;
  loopIteration: number;
}
