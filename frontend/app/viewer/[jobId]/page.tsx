"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams } from "next/navigation";
import {
  StepwiseResult,
  StatusResponse,
  ViewPreset,
  DetailLayer,
  PersonPose,
} from "@/lib/types";
import { POLL_INTERVAL, SPEED_RAMP, PROCESSING_STEPS } from "@/lib/constants";
import { ProcessingStatus } from "@/components/ProcessingStatus";
import { ViewPresetBar } from "@/components/ViewPresetBar";
import { ViewLayout } from "@/components/ViewLayout";
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
  const [activePreset, setActivePreset] = useState<ViewPreset>(3);
  const [activeLayers, setActiveLayers] = useState<Set<DetailLayer>>(
    new Set<DetailLayer>()
  );
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [loopStart, setLoopStart] = useState<number | null>(null);
  const [loopEnd, setLoopEnd] = useState<number | null>(null);
  const [loopIteration, setLoopIteration] = useState(0);

  // Mannequin / X-ray state
  const [xrayMode, setXrayMode] = useState(false);
  const [personPoses, setPersonPoses] = useState<PersonPose[]>([]);
  const [mannequinReady, setMannequinReady] = useState(false);

  const animationRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);
  const audioRef = useRef<HTMLAudioElement>(null);

  // Poll for status
  useEffect(() => {
    // Keep polling while loading/processing, or if mannequin upgrade is pending
    const shouldPoll =
      viewState === "loading" ||
      viewState === "processing" ||
      (viewState === "ready" && !mannequinReady);
    if (!shouldPoll) return;

    const poll = async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        const data: StatusResponse = await res.json();

        if (!res.ok) {
          setViewState("error");
          setErrorMsg(data.error_message || data.error || "Job not found");
          return;
        }

        if (data.status === "processing" || data.status === "upgrading") {
          setViewState("processing");
          setStep(data.step || "Processing...");
        } else if (
          data.status === "complete" ||
          data.status === "skeleton_ready" ||
          data.status === "mannequin_ready"
        ) {
          // Fetch skeleton result if not already loaded
          const resultUrl = data.result_url || data.skeleton_result_url;
          if (resultUrl && !result) {
            const resultRes = await fetch(resultUrl);
            const resultData: StepwiseResult = await resultRes.json();
            setResult(resultData);
            setViewState("revealing");

            // Dramatic reveal: hold first frame for 1 second
            setTimeout(() => {
              setViewState("ready");
              setIsPlaying(true);
            }, 1000);
          }

          // Fetch mannequin result when available
          if (data.mannequin_result_url && !mannequinReady) {
            try {
              const mannequinRes = await fetch(data.mannequin_result_url);
              const mannequinData = await mannequinRes.json();
              if (mannequinData.person_poses) {
                setPersonPoses(mannequinData.person_poses);
                setMannequinReady(true);
              }
            } catch {
              // Mannequin data not ready yet — will retry on next poll
            }
          }
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
  }, [jobId, viewState, result, mannequinReady]);

  // Use refs for mutable values so the animation loop doesn't restart on speed/loop changes
  const playbackSpeedRef = useRef(playbackSpeed);
  const loopStartRef = useRef(loopStart);
  const loopEndRef = useRef(loopEnd);
  const playbackTimeRef = useRef(0); // Shared mutable playback time — seekable from outside

  useEffect(() => { playbackSpeedRef.current = playbackSpeed; }, [playbackSpeed]);
  useEffect(() => { loopStartRef.current = loopStart; }, [loopStart]);
  useEffect(() => { loopEndRef.current = loopEnd; }, [loopEnd]);

  // Time-based animation loop — smooth like a video player
  useEffect(() => {
    if (!isPlaying || !result || viewState !== "ready") return;

    const totalFrames = result.frames.length;
    const dur = result.duration;
    let lastTimestamp = performance.now();

    const animate = (now: number) => {
      const deltaMs = now - lastTimestamp;
      lastTimestamp = now;

      // Advance playback time by delta * speed
      playbackTimeRef.current += (deltaMs / 1000) * playbackSpeedRef.current;

      // Handle looping
      const ls = loopStartRef.current;
      const le = loopEndRef.current;
      if (ls !== null && le !== null && playbackTimeRef.current > le) {
        playbackTimeRef.current = ls;
        setLoopIteration((prev) => {
          const newIter = prev + 1;
          const newSpeed = Math.min(
            SPEED_RAMP.maxSpeed,
            SPEED_RAMP.initialSpeed + SPEED_RAMP.increment * newIter
          );
          setPlaybackSpeed(newSpeed);
          return newIter;
        });
      } else if (playbackTimeRef.current >= dur) {
        playbackTimeRef.current = 0;
      }

      // Convert continuous time to frame index
      const frame = Math.round((playbackTimeRef.current / dur) * (totalFrames - 1));
      setCurrentFrame(Math.max(0, Math.min(frame, totalFrames - 1)));

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isPlaying, result, viewState]);

  // Sync audio with current frame + playback speed
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !result) return;

    const targetTime = (currentFrame / Math.max(result.frames.length - 1, 1)) * result.duration;

    // Set playback rate to match skeleton speed — this is how browsers do smooth speed changes
    audio.playbackRate = playbackSpeed;

    // Only seek if >0.15s out of sync
    if (Math.abs(audio.currentTime - targetTime) > 0.15) {
      audio.currentTime = targetTime;
    }

    // Mute when a VideoPanel is visible (presets 3, 5, 6) to avoid double audio
    const videoPresets = [3, 5, 6];
    audio.muted = videoPresets.includes(activePreset);

    if (!isPlaying && !audio.paused) {
      audio.pause();
    } else if (isPlaying && audio.paused) {
      audio.play().catch(() => {});
    }
  }, [currentFrame, isPlaying, activePreset, result, playbackSpeed]);

  // Keyboard shortcut: X key toggles X-ray mode
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "x" || e.key === "X") {
        setXrayMode((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Select view preset
  const selectPreset = useCallback((preset: ViewPreset) => {
    setActivePreset(preset);
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
    // Update shared playback time so animation loop picks up the new position
    if (result) {
      playbackTimeRef.current = (frame / Math.max(result.frames.length - 1, 1)) * result.duration;
    }
  }, [result]);

  // Toggle play/pause
  const handleTogglePlay = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  // Beat click: always seek to that beat + set loop boundaries
  const handleBeatClick = useCallback(
    (timestamp: number) => {
      if (!result) return;

      // Always jump to the clicked beat
      const frame = Math.round((timestamp / result.duration) * (result.frames.length - 1));
      setCurrentFrame(frame);
      playbackTimeRef.current = timestamp;

      // Loop selection: first click = start, second click = end
      if (loopStart === null) {
        setLoopStart(timestamp);
      } else if (loopEnd === null) {
        if (timestamp > loopStart) {
          setLoopEnd(timestamp);
          setLoopIteration(0);
          setPlaybackSpeed(SPEED_RAMP.initialSpeed);
          // Jump to loop start
          const startFrame = Math.round((loopStart / result.duration) * (result.frames.length - 1));
          setCurrentFrame(startFrame);
          playbackTimeRef.current = loopStart;
        } else {
          // Clicked before the start — reset start
          setLoopStart(timestamp);
        }
      } else {
        // Loop already set — reset and start new selection
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

  // Speed change
  const handleSpeedChange = useCallback((speed: number) => {
    setPlaybackSpeed(speed);
  }, []);

  // Prev beat navigation
  const handlePrevBeat = useCallback(() => {
    if (!result) return;
    const currentTime = (currentFrame / Math.max(result.frames.length - 1, 1)) * result.duration;
    const prevBeat = [...(result.beats || [])].reverse().find(b => b.timestamp < currentTime - 0.05);
    if (prevBeat) {
      const frame = Math.round((prevBeat.timestamp / result.duration) * (result.frames.length - 1));
      setCurrentFrame(frame);
    }
  }, [result, currentFrame]);

  // Next beat navigation
  const handleNextBeat = useCallback(() => {
    if (!result) return;
    const currentTime = (currentFrame / Math.max(result.frames.length - 1, 1)) * result.duration;
    const nextBeat = (result.beats || []).find(b => b.timestamp > currentTime + 0.05);
    if (nextBeat) {
      const frame = Math.round((nextBeat.timestamp / result.duration) * (result.frames.length - 1));
      setCurrentFrame(frame);
    }
  }, [result, currentFrame]);

  // Compute active beat index
  const activeBeatIndex = useMemo(() => {
    if (!result?.beats?.length) return -1;
    const currentTime = (currentFrame / Math.max(result.frames.length - 1, 1)) * result.duration;
    let idx = -1;
    for (let i = 0; i < result.beats.length; i++) {
      if (result.beats[i].timestamp <= currentTime + 0.05) idx = i;
      else break;
    }
    return idx;
  }, [result, currentFrame]);

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
          <p className="font-display text-text-primary text-xl mb-2">Processing failed</p>
          <p className="text-text-secondary mb-6">{errorMsg}</p>
          <a
            href="/"
            className="inline-block px-5 py-2 rounded-button bg-accent text-bg font-semibold text-sm font-display hover:brightness-110 transition-all duration-150"
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

  return (
    <div className="h-screen flex flex-col bg-bg">
      {/* View preset bar */}
      <ViewPresetBar
        activePreset={activePreset}
        activeLayers={activeLayers}
        onSelectPreset={selectPreset}
        onToggleLayer={toggleLayer}
        xrayMode={xrayMode}
        onXrayToggle={() => setXrayMode((prev) => !prev)}
        hasMannequinData={mannequinReady}
      />

      {/* View layout */}
      <div className="flex-1 min-h-0 p-1" style={{ height: "70vh" }}>
        <ViewLayout
          activePreset={activePreset}
          frames={result.frames}
          currentFrame={currentFrame}
          showHands={showHands}
          showFeet={showFeet}
          isPaused={!isPlaying}
          videoUrl={result.video_url || undefined}
          duration={result.duration}
          playbackSpeed={playbackSpeed}
          personPoses={personPoses}
          focusedPersonId={0}
          xrayMode={xrayMode}
        />
      </div>

      {/* Hidden audio element for skeleton-only presets */}
      <audio
        ref={audioRef}
        src={result.video_url || undefined}
        preload="auto"
      />

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
        onPrevBeat={handlePrevBeat}
        onNextBeat={handleNextBeat}
        activeBeatIndex={activeBeatIndex}
        onSpeedChange={handleSpeedChange}
      />
    </div>
  );
}
