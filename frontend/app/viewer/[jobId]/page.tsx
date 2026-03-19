"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import {
  StepwiseResult,
  StatusResponse,
  CameraAngle,
  DetailLayer,
} from "@/lib/types";
import { POLL_INTERVAL, SPEED_RAMP, PROCESSING_STEPS } from "@/lib/constants";
import { ProcessingStatus } from "@/components/ProcessingStatus";
import { CameraAngleBar } from "@/components/CameraAngleBar";
import { PanelGrid } from "@/components/PanelGrid";
import { SkeletonViewer } from "@/components/SkeletonViewer";
import { GhostOverlay } from "@/components/GhostOverlay";
import { Timeline } from "@/components/Timeline";

type ViewState = "loading" | "processing" | "revealing" | "ready" | "error";

export default function ViewerPage() {
  const params = useParams();
  const jobId = params.jobId as string;

  // Status polling
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [step, setStep] = useState("Initializing...");
  const [errorMsg, setErrorMsg] = useState("");
  const [result, setResult] = useState<StepwiseResult | null>(null);

  // Viewer state
  const [activeAngles, setActiveAngles] = useState<Set<CameraAngle>>(
    new Set<CameraAngle>(["front"])
  );
  const [activeLayers, setActiveLayers] = useState<Set<DetailLayer>>(
    new Set<DetailLayer>()
  );
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [loopStart, setLoopStart] = useState<number | null>(null);
  const [loopEnd, setLoopEnd] = useState<number | null>(null);
  const [loopIteration, setLoopIteration] = useState(0);

  const animationRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);

  // Poll for status
  useEffect(() => {
    if (viewState !== "loading" && viewState !== "processing") return;

    const poll = async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        const data: StatusResponse = await res.json();

        if (!res.ok) {
          setViewState("error");
          setErrorMsg(data.error_message || data.error || "Job not found");
          return;
        }

        if (data.status === "processing") {
          setViewState("processing");
          setStep(data.step || "Processing...");
        } else if (data.status === "complete" && data.result_url) {
          // Fetch the result data
          const resultRes = await fetch(data.result_url);
          const resultData: StepwiseResult = await resultRes.json();
          setResult(resultData);
          setViewState("revealing");

          // Dramatic reveal: hold first frame for 1 second
          setTimeout(() => {
            setViewState("ready");
            setIsPlaying(true);
          }, 1000);
        } else if (data.status === "error") {
          setViewState("error");
          setErrorMsg(data.error_message || "Something went wrong");
        }
      } catch {
        // Retry on network errors
      }
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [jobId, viewState]);

  // Animation loop
  useEffect(() => {
    if (!isPlaying || !result || viewState !== "ready") return;

    const fps = result.fps;
    const totalFrames = result.frames.length;
    const frameDuration = 1000 / (fps * playbackSpeed);

    let lastTime = performance.now();

    const animate = (time: number) => {
      const delta = time - lastTime;

      if (delta >= frameDuration) {
        lastTime = time - (delta % frameDuration);

        setCurrentFrame((prev) => {
          let next = prev + 1;

          // Handle looping
          if (loopStart !== null && loopEnd !== null && result) {
            const loopStartFrame = Math.round(
              (loopStart / result.duration) * (totalFrames - 1)
            );
            const loopEndFrame = Math.round(
              (loopEnd / result.duration) * (totalFrames - 1)
            );

            if (next > loopEndFrame) {
              next = loopStartFrame;
              // Increment loop iteration and ramp speed
              setLoopIteration((prev) => {
                const newIter = prev + 1;
                const newSpeed = Math.min(
                  SPEED_RAMP.maxSpeed,
                  SPEED_RAMP.initialSpeed +
                    SPEED_RAMP.increment * newIter
                );
                setPlaybackSpeed(newSpeed);
                return newIter;
              });
            }
          } else if (next >= totalFrames) {
            next = 0;
          }

          return next;
        });
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, result, viewState, playbackSpeed, loopStart, loopEnd]);

  // Toggle camera angle
  const toggleAngle = useCallback((angle: CameraAngle) => {
    setActiveAngles((prev) => {
      const next = new Set(prev);
      if (next.has(angle)) {
        if (next.size > 1) next.delete(angle);
      } else {
        if (next.size >= 4) return next; // max 4 panels
        next.add(angle);
      }
      return next;
    });
  }, []);

  // Toggle detail layer
  const toggleLayer = useCallback((layer: DetailLayer) => {
    setActiveLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) {
        next.delete(layer);
      } else {
        next.add(layer);
      }
      return next;
    });
  }, []);

  // Seek
  const handleSeek = useCallback((frame: number) => {
    setCurrentFrame(frame);
  }, []);

  // Toggle play/pause
  const handleTogglePlay = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  // Beat click for loop
  const handleBeatClick = useCallback(
    (timestamp: number) => {
      if (!result) return;

      if (loopStart === null) {
        setLoopStart(timestamp);
      } else if (loopEnd === null) {
        if (timestamp > loopStart) {
          setLoopEnd(timestamp);
          setLoopIteration(0);
          setPlaybackSpeed(SPEED_RAMP.initialSpeed);
        } else {
          setLoopStart(timestamp);
        }
      } else {
        // Reset and start new loop selection
        setLoopStart(timestamp);
        setLoopEnd(null);
        setLoopIteration(0);
        setPlaybackSpeed(1.0);
      }
    },
    [result, loopStart, loopEnd]
  );

  // Clear loop
  const handleClearLoop = useCallback(() => {
    setLoopStart(null);
    setLoopEnd(null);
    setLoopIteration(0);
    setPlaybackSpeed(1.0);
  }, []);

  // Processing or loading state
  if (viewState === "loading" || viewState === "processing") {
    const stepIndex = PROCESSING_STEPS.findIndex((s) => s === step);
    return (
      <ProcessingStatus
        step={step}
        currentStepIndex={stepIndex >= 0 ? stepIndex : 0}
        totalSteps={PROCESSING_STEPS.length}
      />
    );
  }

  // Error state
  if (viewState === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg">
        <div className="text-center">
          <div className="text-error text-6xl mb-4">!</div>
          <p className="text-text-primary text-xl mb-2">Processing failed</p>
          <p className="text-text-secondary mb-6">{errorMsg}</p>
          <a
            href="/"
            className="inline-block px-5 py-2 rounded-button bg-accent text-bg font-semibold text-sm hover:brightness-110 transition-all duration-150"
          >
            Back to home
          </a>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const showHands = activeLayers.has("hands");
  const showFeet = activeLayers.has("footwork");

  const labelMap: Record<CameraAngle, string> = {
    video: "Video",
    front: "Front",
    back: "Back",
    mirror: "Mirror",
    ghost: "Ghost",
  };

  // All possible camera angles — we render ALL panels persistently so
  // WebGL contexts are never destroyed/recreated on toggle. PanelGrid
  // hides inactive panels with CSS display:none instead of unmounting.
  const ALL_ANGLES: CameraAngle[] = ["video", "front", "back", "mirror", "ghost"];

  const allPanelEntries = ALL_ANGLES.map((angle) => {
    if (angle === "video") {
      return {
        key: angle,
        label: labelMap[angle],
        content: (
          <div className="w-full h-full flex items-center justify-center text-text-secondary text-sm">
            Video panel (source video will appear here)
          </div>
        ),
      };
    }

    if (angle === "ghost") {
      return {
        key: angle,
        label: labelMap[angle],
        content: (
          <GhostOverlay
            frames={result.frames}
            currentFrame={currentFrame}
            showHands={showHands}
            showFeet={showFeet}
          />
        ),
      };
    }

    return {
      key: angle,
      label: labelMap[angle],
      content: (
        <SkeletonViewer
          frames={result.frames}
          currentFrame={currentFrame}
          angle={angle}
          showHands={showHands}
          showFeet={showFeet}
        />
      ),
    };
  });

  const visibleKeys = new Set<string>(activeAngles);

  return (
    <div className="h-screen flex flex-col bg-bg">
      {/* Camera angle bar */}
      <CameraAngleBar
        activeAngles={activeAngles}
        activeLayers={activeLayers}
        onToggleAngle={toggleAngle}
        onToggleLayer={toggleLayer}
      />

      {/* Panel grid - 70% viewport height */}
      <div className="flex-1 min-h-0 p-1" style={{ height: "70vh" }}>
        <PanelGrid panels={allPanelEntries} visibleKeys={visibleKeys} />
      </div>

      {/* Timeline */}
      <Timeline
        currentFrame={currentFrame}
        totalFrames={result.frames.length}
        duration={result.duration}
        beats={result.beats}
        difficulty={result.difficulty}
        isPlaying={isPlaying}
        loopStart={loopStart}
        loopEnd={loopEnd}
        onSeek={handleSeek}
        onTogglePlay={handleTogglePlay}
        onBeatClick={handleBeatClick}
        onClearLoop={handleClearLoop}
        playbackSpeed={playbackSpeed}
        loopIteration={loopIteration}
      />
    </div>
  );
}
