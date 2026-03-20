"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { ViewPreset, PoseFrame } from "@/lib/types";
import { SkeletonViewer } from "./SkeletonViewer";

function VideoPanel({
  videoUrl,
  currentFrame,
  totalFrames,
  duration,
  isPaused,
  playbackSpeed = 1.0,
  className,
  onVideoMeta,
  videoRef: externalVideoRef,
}: {
  videoUrl?: string;
  currentFrame: number;
  totalFrames: number;
  duration: number;
  isPaused: boolean;
  playbackSpeed?: number;
  className?: string;
  onVideoMeta?: (width: number, height: number) => void;
  videoRef?: React.RefObject<HTMLVideoElement>;
}) {
  const internalVideoRef = useRef<HTMLVideoElement>(null);
  const videoRef = externalVideoRef || internalVideoRef;

  // Report video natural dimensions when metadata loads
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !onVideoMeta) return;
    const handler = () => onVideoMeta(video.videoWidth, video.videoHeight);
    if (video.videoWidth > 0) handler();
    video.addEventListener("loadedmetadata", handler);
    return () => video.removeEventListener("loadedmetadata", handler);
  }, [videoRef, onVideoMeta]);

  // Sync video playback with skeleton frame and speed
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !duration) return;

    // Set playback rate for smooth speed changes (browser handles interpolation)
    video.playbackRate = playbackSpeed;

    const targetTime = (currentFrame / Math.max(totalFrames - 1, 1)) * duration;

    // Only seek if we're more than 0.1s out of sync
    if (Math.abs(video.currentTime - targetTime) > 0.1) {
      video.currentTime = targetTime;
    }

    if (isPaused && !video.paused) {
      video.pause();
    } else if (!isPaused && video.paused) {
      video.play().catch(() => {}); // Autoplay may be blocked
    }
  }, [currentFrame, totalFrames, duration, isPaused, playbackSpeed]);

  if (!videoUrl) {
    return (
      <div className={`bg-surface flex flex-col items-center justify-center text-text-secondary ${className || ""}`}>
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
    );
  }

  return (
    <div className={`bg-black flex items-center justify-center ${className || ""}`}>
      <video
        ref={videoRef}
        src={videoUrl}
        className="w-full h-full object-contain"
        playsInline
        muted={false}
        preload="auto"
        crossOrigin="anonymous"
      />
    </div>
  );
}

function ViewLabel({ label }: { label: string }) {
  return (
    <div
      className="absolute top-2 left-2 z-10 pointer-events-none select-none"
      style={{
        fontFamily: "var(--font-geist-mono, 'Geist Mono', monospace)",
        fontSize: "11px",
        color: "rgba(255,255,255,0.5)",
        backgroundColor: "rgba(0,0,0,0.4)",
        padding: "2px 6px",
        borderRadius: "4px",
      }}
    >
      {label}
    </div>
  );
}

/** Compute where object-contain places the video inside a container */
function computeContainedRect(
  containerW: number,
  containerH: number,
  videoW: number,
  videoH: number
) {
  const containerAspect = containerW / containerH;
  const videoAspect = videoW / videoH;
  let renderW: number, renderH: number, offsetX: number, offsetY: number;
  if (videoAspect > containerAspect) {
    // Video is wider — letterboxed (bars top/bottom)
    renderW = containerW;
    renderH = containerW / videoAspect;
    offsetX = 0;
    offsetY = (containerH - renderH) / 2;
  } else {
    // Video is taller — pillarboxed (bars left/right)
    renderH = containerH;
    renderW = containerH * videoAspect;
    offsetX = (containerW - renderW) / 2;
    offsetY = 0;
  }
  return { renderW, renderH, offsetX, offsetY };
}

function GhostOverlay({
  videoUrl,
  currentFrame,
  totalFrames,
  duration,
  isPaused,
  playbackSpeed,
  frames,
  showHands,
  showFeet,
}: {
  videoUrl?: string;
  currentFrame: number;
  totalFrames: number;
  duration: number;
  isPaused: boolean;
  playbackSpeed: number;
  frames: PoseFrame[];
  showHands: boolean;
  showFeet: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const ghostVideoRef = useRef<HTMLVideoElement>(null!);

  const [videoNatural, setVideoNatural] = useState<{ w: number; h: number } | null>(null);
  const [containerSize, setContainerSize] = useState<{ w: number; h: number } | null>(null);

  const handleVideoMeta = useCallback((w: number, h: number) => {
    setVideoNatural({ w, h });
  }, []);

  // Track container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setContainerSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Compute skeleton rect to match video's rendered area
  const skeletonStyle = (() => {
    if (!videoNatural || !containerSize) {
      return { position: "absolute" as const, inset: 0 };
    }
    const { renderW, renderH, offsetX, offsetY } = computeContainedRect(
      containerSize.w,
      containerSize.h,
      videoNatural.w,
      videoNatural.h
    );
    return {
      position: "absolute" as const,
      left: offsetX,
      top: offsetY,
      width: renderW,
      height: renderH,
    };
  })();

  return (
    <div ref={containerRef} className="relative w-full h-full bg-black">
      <ViewLabel label="Ghost" />
      {/* Video layer — dimmed so skeleton is clearly visible */}
      <div className="absolute inset-0" style={{ opacity: 0.35 }}>
        <VideoPanel
          videoUrl={videoUrl}
          currentFrame={currentFrame}
          totalFrames={totalFrames}
          duration={duration}
          isPaused={isPaused}
          playbackSpeed={playbackSpeed}
          className="w-full h-full"
          onVideoMeta={handleVideoMeta}
          videoRef={ghostVideoRef}
        />
      </div>
      {/* Skeleton overlay — positioned to match the video's rendered area */}
      <div style={skeletonStyle}>
        <SkeletonViewer
          frames={frames}
          currentFrame={currentFrame}
          angle="front"
          showHands={showHands}
          showFeet={showFeet}
          groundToFloor={false}
          orbitEnabled={false}
        />
      </div>
    </div>
  );
}

interface ViewLayoutProps {
  activePreset: ViewPreset;
  frames: PoseFrame[];
  currentFrame: number;
  showHands: boolean;
  showFeet: boolean;
  isPaused: boolean;
  videoUrl?: string;
  duration?: number;
  playbackSpeed?: number;
}

export function ViewLayout({
  activePreset,
  frames,
  currentFrame,
  showHands,
  showFeet,
  isPaused,
  videoUrl,
  duration = 0,
  playbackSpeed = 1.0,
}: ViewLayoutProps) {
  const totalFrames = frames.length;
  switch (activePreset) {
    // Preset 1: Front — full-screen front view
    case 1:
      return (
        <div className="relative w-full h-full">
          <ViewLabel label="Front" />
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
        <div className="relative w-full h-full">
          <ViewLabel label="Mirror" />
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
          <div className="relative w-1/2 h-full border-r border-border">
            <ViewLabel label="Original" />
            <VideoPanel
              videoUrl={videoUrl}
              currentFrame={currentFrame}
              totalFrames={totalFrames}
              duration={duration}
              isPaused={isPaused}
              playbackSpeed={playbackSpeed}
              className="w-full h-full"
            />
          </div>
          <div className="relative w-1/2 h-full">
            <ViewLabel label="Front" />
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
          <div className="relative w-1/2 h-full border-r border-border">
            <ViewLabel label="Front" />
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
            />
          </div>
          <div className="relative w-1/2 h-full">
            <ViewLabel label="Back" />
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

    // Preset 5: Ghost Overlay — dimmed video with bright skeleton on top
    case 5:
      return (
        <GhostOverlay
          videoUrl={videoUrl}
          currentFrame={currentFrame}
          totalFrames={totalFrames}
          duration={duration}
          isPaused={isPaused}
          playbackSpeed={playbackSpeed}
          frames={frames}
          showHands={showHands}
          showFeet={showFeet}
        />
      );

    // Preset 6: Video + PiP — video fullscreen, small skeleton in bottom-right
    case 6:
      return (
        <div className="relative w-full h-full">
          <ViewLabel label="Original" />
          {/* Full video */}
          <VideoPanel
            videoUrl={videoUrl}
            currentFrame={currentFrame}
            totalFrames={totalFrames}
            duration={duration}
            isPaused={isPaused}
            playbackSpeed={playbackSpeed}
            className="absolute inset-0"
          />
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
            <ViewLabel label="Front" />
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
          <ViewLabel label={isPaused ? "Freeze — drag to orbit" : "Freeze"} />
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
          <div className="relative w-1/2 h-full border-r border-border">
            <ViewLabel label="Front" />
            <SkeletonViewer
              frames={frames}
              currentFrame={currentFrame}
              angle="front"
              showHands={showHands}
              showFeet={showFeet}
              mirrored={false}
            />
          </div>
          <div className="relative w-1/2 h-full">
            <ViewLabel label="Mirror" />
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
