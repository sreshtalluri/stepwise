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
      <div className="absolute inset-0 bg-[#141414] flex flex-col items-center justify-center">
        {videoUrl ? (
          <div className="text-text-secondary text-sm">Video playback</div>
        ) : (
          <>
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#888888"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mb-3 opacity-60"
            >
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            <p className="text-[#888888] text-sm">Ghost mode requires a video source</p>
          </>
        )}
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
