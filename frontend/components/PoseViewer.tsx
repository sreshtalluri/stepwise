"use client";

import { PoseFrame, PersonPose, CameraAngle } from "@/lib/types";
import { SkeletonViewer } from "./SkeletonViewer";
import { MannequinViewer } from "./MannequinViewer";

interface PoseViewerProps {
  // Skeleton data (always available)
  frames: PoseFrame[];
  currentFrame: number;
  angle: CameraAngle;
  showHands: boolean;
  showFeet: boolean;
  mirror?: boolean;
  mirrored?: boolean;
  orbitEnabled?: boolean;
  opacity?: number;
  groundToFloor?: boolean;

  // Mannequin data (available after SMPL-X processing)
  personPoses?: PersonPose[];
  focusedPersonId?: number;
  beatPulse?: boolean;

  // View mode
  xrayMode: boolean; // true = skeleton, false = mannequin
}

export function PoseViewer({
  frames,
  currentFrame,
  angle,
  showHands,
  showFeet,
  mirror,
  mirrored,
  orbitEnabled,
  opacity,
  groundToFloor,
  personPoses,
  focusedPersonId = 0,
  beatPulse = false,
  xrayMode,
}: PoseViewerProps) {
  // If no mannequin data available, always show skeleton
  const hasMannequinData = personPoses && personPoses.length > 0;
  const showSkeleton = xrayMode || !hasMannequinData;

  if (showSkeleton) {
    return (
      <SkeletonViewer
        frames={frames}
        currentFrame={currentFrame}
        angle={angle}
        showHands={showHands}
        showFeet={showFeet}
        mirror={mirror}
        mirrored={mirrored}
        orbitEnabled={orbitEnabled}
        opacity={opacity}
        groundToFloor={groundToFloor}
      />
    );
  }

  return (
    <MannequinViewer
      personPoses={personPoses!}
      currentFrame={currentFrame}
      angle={angle}
      focusedPersonId={focusedPersonId}
      mirror={mirrored}
      opacity={opacity}
      groundToFloor={groundToFloor}
      beatPulse={beatPulse}
    />
  );
}
