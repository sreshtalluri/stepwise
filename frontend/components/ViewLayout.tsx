"use client";

import { ViewPreset, PoseFrame } from "@/lib/types";
import { SkeletonViewer } from "./SkeletonViewer";

interface ViewLayoutProps {
  activePreset: ViewPreset;
  frames: PoseFrame[];
  currentFrame: number;
  showHands: boolean;
  showFeet: boolean;
  isPaused: boolean;
}

export function ViewLayout({
  activePreset,
  frames,
  currentFrame,
  showHands,
  showFeet,
  isPaused,
}: ViewLayoutProps) {
  switch (activePreset) {
    // Preset 1: Front — full-screen front view
    case 1:
      return (
        <div className="w-full h-full">
          <SkeletonViewer
            frames={frames}
            currentFrame={currentFrame}
            angle="front"
            showHands={showHands}
            showFeet={showFeet}
          />
        </div>
      );

    // Preset 2: Mirror — full-screen mirrored view
    case 2:
      return (
        <div className="w-full h-full">
          <SkeletonViewer
            frames={frames}
            currentFrame={currentFrame}
            angle="front"
            showHands={showHands}
            showFeet={showFeet}
            mirrored={true}
          />
        </div>
      );

    // Preset 3: Side by Side — video left, front skeleton right (DEFAULT)
    case 3:
      return (
        <div className="flex w-full h-full">
          <div className="w-1/2 h-full bg-surface flex items-center justify-center border-r border-border">
            <div className="text-text-secondary text-sm flex flex-col items-center gap-3">
              <svg
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="opacity-60"
              >
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
              <span>Original video</span>
            </div>
          </div>
          <div className="w-1/2 h-full">
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

    // Preset 4: Front + Back — front left, back right
    case 4:
      return (
        <div className="flex w-full h-full">
          <div className="w-1/2 h-full border-r border-border">
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
            />
          </div>
          <div className="w-1/2 h-full">
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="back"
              showHands={showHands}
              showFeet={showFeet}
            />
          </div>
        </div>
      );

    // Preset 5: Ghost Overlay — skeleton at 50% opacity over video
    case 5:
      return (
        <div className="relative w-full h-full">
          {/* Video layer (placeholder) */}
          <div className="absolute inset-0 bg-surface flex flex-col items-center justify-center text-text-secondary">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mb-3 opacity-60"
            >
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            <p className="text-sm">Original video</p>
          </div>
          {/* Skeleton overlay at 50% opacity */}
          <div className="absolute inset-0">
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
              opacity={0.5}
            />
          </div>
        </div>
      );

    // Preset 6: Video + PiP — video fullscreen, small skeleton in bottom-right
    case 6:
      return (
        <div className="relative w-full h-full">
          {/* Full video (placeholder) */}
          <div className="absolute inset-0 bg-surface flex flex-col items-center justify-center text-text-secondary">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mb-3 opacity-60"
            >
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            <p className="text-sm">Original video</p>
          </div>
          {/* PiP skeleton in bottom-right corner */}
          <div
            className="absolute bottom-4 right-4 overflow-hidden"
            style={{
              width: "25%",
              aspectRatio: "4/3",
              backgroundColor: "#141414",
              border: "1px solid #222222",
              borderRadius: "12px",
            }}
          >
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

    // Preset 7: Freeze Compare — front view, orbit unlocks when paused
    case 7:
      return (
        <div className="relative w-full h-full">
          <SkeletonViewer
            frames={frames}
            currentFrame={currentFrame}
            angle="front"
            showHands={showHands}
            showFeet={showFeet}
            orbitEnabled={isPaused}
          />
          {isPaused && (
            <div
              className="absolute bottom-6 left-1/2 -translate-x-1/2 pointer-events-none select-none"
              style={{
                fontFamily: "var(--font-geist-mono, 'Geist Mono', monospace)",
                fontSize: "12px",
                color: "#888888",
              }}
            >
              Drag to rotate
            </div>
          )}
        </div>
      );

    // Preset 8: Split Mirror — front left, mirrored right
    case 8:
      return (
        <div className="flex w-full h-full">
          <div className="w-1/2 h-full border-r border-border">
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
              mirrored={false}
            />
          </div>
          <div className="w-1/2 h-full">
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
              mirrored={true}
            />
          </div>
        </div>
      );

    default:
      return null;
  }
}
