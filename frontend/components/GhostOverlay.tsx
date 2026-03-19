"use client";

import { PoseFrame } from "@/lib/types";
import { SkeletonViewer } from "./SkeletonViewer";

interface GhostOverlayProps {
  frames: PoseFrame[];
  currentFrame: number;
  showHands: boolean;
  showFeet: boolean;
  videoUrl?: string;
}

export function GhostOverlay({
  frames,
  currentFrame,
  showHands,
  showFeet,
  videoUrl,
}: GhostOverlayProps) {
  return (
    <div className="relative w-full h-full">
      {/* Video layer (placeholder) */}
      <div className="absolute inset-0 bg-surface flex items-center justify-center">
        <div className="text-text-secondary text-sm">
          {videoUrl ? "Video playback" : "No video source"}
        </div>
      </div>

      {/* Skeleton overlay at 50% opacity */}
      <div className="absolute inset-0" style={{ opacity: 0.5 }}>
        <SkeletonViewer
          frames={frames}
          currentFrame={currentFrame}
          angle="front"
          showHands={showHands}
          showFeet={showFeet}
        />
      </div>
    </div>
  );
}
