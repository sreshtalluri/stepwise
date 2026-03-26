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
  joints_3d?: Record<JointName, Joint>;
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
  video_url?: string | null; // Direct video CDN URL for playback
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

// SMPL/SMPL-X body model parameters (v2)
export interface SmplxParams {
  betas: number[];        // body shape (10 values)
  body_pose: number[];    // joint rotations: SMPL 69 (23×3) or SMPL-X 63 (21×3)
  left_hand_pose: number[];  // SMPL-X: 45 values (15 joints × 3), SMPL: empty
  right_hand_pose: number[]; // SMPL-X: 45 values (15 joints × 3), SMPL: empty
  global_orient: number[];   // root orientation (3 values)
  transl: number[];          // root translation (3 values)
}

export interface PersonPose {
  person_id: number;
  frame: number;
  timestamp: number;
  smplx_params: SmplxParams;
}

export interface BodyPartScores {
  arms: number;  // 0-1
  legs: number;  // 0-1
  core: number;  // 0-1
}

export interface BodyPartDifficultyFrame {
  frame: number;
  overall: number;  // 0-1
  body_parts: BodyPartScores;
}

export interface BodyPartDifficulty {
  overall: number;
  per_frame: BodyPartDifficultyFrame[];
}

export interface StepwiseResultV2 extends Omit<StepwiseResult, "version"> {
  version: "2.0";
  person_count: number;
  person_poses: PersonPose[];
  body_part_difficulty: BodyPartDifficulty;
}

export interface StatusResponse {
  status: "processing" | "skeleton_ready" | "upgrading" | "mannequin_ready" | "complete" | "error";
  step?: string;
  result_url?: string;
  skeleton_result_url?: string;
  mannequin_result_url?: string;
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
