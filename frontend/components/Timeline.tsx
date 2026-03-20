"use client";

import { useCallback, useRef, useState, MouseEvent } from "react";
import { Beat, DifficultySegment } from "@/lib/types";

interface TimelineProps {
  currentFrame: number;
  totalFrames: number;
  duration: number;
  beats: Beat[];
  difficulty: DifficultySegment[];
  isPlaying: boolean;
  loopStart: number | null;
  loopEnd: number | null;
  onSeek: (frame: number) => void;
  onTogglePlay: () => void;
  onBeatClick: (timestamp: number) => void;
  onClearLoop: () => void;
  onLoopDrag: (startTime: number, endTime: number) => void;
  playbackSpeed: number;
  loopIteration: number;
  loopSpeedUp: boolean;
  onToggleLoopSpeedUp: () => void;
  onPrevBeat?: () => void;
  onNextBeat?: () => void;
  activeBeatIndex?: number;
  onSpeedChange?: (speed: number) => void;
}

function difficultyColor(score: number): string {
  if (score < 0.4) return "#44ff88";
  if (score < 0.7) return "#ffdd44";
  return "#ff4444";
}

// Minimum pixel distance to distinguish drag from click
const DRAG_THRESHOLD = 5;

function snapToNearestBeat(time: number, beats: Beat[]): number {
  if (beats.length === 0) return time;
  let closest = beats[0].timestamp;
  let minDist = Math.abs(time - closest);
  for (const beat of beats) {
    const dist = Math.abs(time - beat.timestamp);
    if (dist < minDist) {
      minDist = dist;
      closest = beat.timestamp;
    }
  }
  return closest;
}

export function Timeline({
  currentFrame,
  totalFrames,
  duration,
  beats,
  difficulty,
  isPlaying,
  loopStart,
  loopEnd,
  onSeek,
  onTogglePlay,
  onBeatClick,
  onClearLoop,
  onLoopDrag,
  playbackSpeed,
  loopIteration,
  loopSpeedUp,
  onToggleLoopSpeedUp,
  onPrevBeat,
  onNextBeat,
  activeBeatIndex,
  onSpeedChange,
}: TimelineProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const progress = totalFrames > 0 ? currentFrame / (totalFrames - 1) : 0;
  const currentTime = duration * progress;

  // Drag-to-loop state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartTime, setDragStartTime] = useState<number | null>(null);
  const [dragCurrentTime, setDragCurrentTime] = useState<number | null>(null);
  // Track whether the mousedown resulted in a real drag (moved beyond threshold)
  const didDragRef = useRef(false);

  const handleBarMouseDown = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      if (!barRef.current) return;

      const rect = barRef.current.getBoundingClientRect();
      const startX = e.clientX;
      const x = Math.max(0, Math.min(1, (startX - rect.left) / rect.width));
      const time = x * duration;

      didDragRef.current = false;
      setDragStartTime(time);
      setDragCurrentTime(time);

      const handleMouseMove = (me: globalThis.MouseEvent) => {
        const dist = Math.abs(me.clientX - startX);
        if (dist >= DRAG_THRESHOLD) {
          didDragRef.current = true;
          setIsDragging(true);
        }
        if (!barRef.current) return;
        const r = barRef.current.getBoundingClientRect();
        const mx = Math.max(0, Math.min(1, (me.clientX - r.left) / r.width));
        setDragCurrentTime(mx * duration);
      };

      const handleMouseUp = (me: globalThis.MouseEvent) => {
        window.removeEventListener("mousemove", handleMouseMove);
        window.removeEventListener("mouseup", handleMouseUp);

        if (didDragRef.current && barRef.current) {
          // Drag completed — snap to nearest beats and create loop
          const r = barRef.current.getBoundingClientRect();
          const mx = Math.max(0, Math.min(1, (me.clientX - r.left) / r.width));
          const endTime = mx * duration;

          const rawStart = Math.min(time, endTime);
          const rawEnd = Math.max(time, endTime);
          const snappedStart = snapToNearestBeat(rawStart, beats);
          const snappedEnd = snapToNearestBeat(rawEnd, beats);

          if (snappedStart < snappedEnd) {
            onLoopDrag(snappedStart, snappedEnd);
          }
        } else {
          // Click — seek to position
          if (barRef.current) {
            const r = barRef.current.getBoundingClientRect();
            const mx = (me.clientX - r.left) / r.width;
            const frame = Math.round(mx * (totalFrames - 1));
            onSeek(Math.max(0, Math.min(frame, totalFrames - 1)));
          }
        }

        setIsDragging(false);
        setDragStartTime(null);
        setDragCurrentTime(null);
      };

      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    },
    [duration, beats, totalFrames, onLoopDrag, onSeek]
  );

  // Compute drag preview region (snapped to beats)
  const dragPreview = (() => {
    if (!isDragging || dragStartTime === null || dragCurrentTime === null) return null;
    const rawLeft = Math.min(dragStartTime, dragCurrentTime);
    const rawRight = Math.max(dragStartTime, dragCurrentTime);
    const left = snapToNearestBeat(rawLeft, beats);
    const right = snapToNearestBeat(rawRight, beats);
    if (left >= right) return null;
    return { left, right };
  })();

  const formatTime = (t: number) => {
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    const ms = Math.floor((t % 1) * 10);
    return `${mins}:${secs.toString().padStart(2, "0")}.${ms}`;
  };

  return (
    <div className="bg-surface border-t border-border px-4 py-3">
      {/* Controls row */}
      <div className="flex items-center gap-3 mb-2">
        {/* Prev beat */}
        <button
          onClick={onPrevBeat}
          className="w-8 h-8 flex items-center justify-center rounded-button text-accent hover:bg-accent-glow transition-colors"
          title="Previous beat (Left arrow)"
        >
          <span className="text-sm">&#9664;</span>
        </button>

        {/* Play/Pause */}
        <button
          onClick={onTogglePlay}
          className="w-8 h-8 flex items-center justify-center rounded-button text-accent hover:bg-accent-glow transition-colors"
          title="Play/Pause (Space)"
        >
          {isPlaying ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              <rect x="1" y="1" width="4" height="12" rx="1" />
              <rect x="9" y="1" width="4" height="12" rx="1" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              <path d="M2 1l11 6-11 6V1z" />
            </svg>
          )}
        </button>

        {/* Next beat */}
        <button
          onClick={onNextBeat}
          className="w-8 h-8 flex items-center justify-center rounded-button text-accent hover:bg-accent-glow transition-colors"
          title="Next beat (Right arrow)"
        >
          <span className="text-sm">&#9654;</span>
        </button>

        {/* Time display */}
        <span className="text-text-secondary text-xs font-mono min-w-[80px] tabular-nums">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Loop status + speed-up toggle */}
        {loopStart !== null && loopEnd !== null ? (
          <div className="flex items-center gap-2">
            <button
              onClick={onClearLoop}
              className="text-xs text-accent bg-accent-glow px-2 py-1 rounded-button hover:brightness-110 transition-all"
              title="Click to clear loop (Esc)"
            >
              &#x1f501; Loop x{loopIteration + 1} &times;
            </button>
            <button
              onClick={onToggleLoopSpeedUp}
              className={`text-xs px-2 py-1 rounded-button border transition-all ${
                loopSpeedUp
                  ? "text-accent border-accent bg-accent-glow"
                  : "text-text-tertiary border-border hover:text-text-secondary"
              }`}
              title="Auto speed-up each loop iteration"
            >
              {loopSpeedUp ? "Ramp On" : "Ramp Off"}
            </button>
          </div>
        ) : isDragging ? (
          <span className="text-xs text-accent animate-pulse">
            Drag to set loop region...
          </span>
        ) : (
          <span className="text-xs text-text-tertiary">
            Drag to loop a section
          </span>
        )}

        {/* Speed control */}
        {onSpeedChange && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => onSpeedChange(Math.max(0.25, playbackSpeed - 0.25))}
              className="w-6 h-6 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors text-xs"
              title="Slow down"
            >
              -
            </button>
            <div
              className={`text-xs font-mono px-2 py-1 rounded-button border ${
                loopSpeedUp && loopIteration > 0
                  ? "speed-pulse text-accent border-accent"
                  : "text-text-secondary border-border"
              }`}
            >
              {playbackSpeed.toFixed(2)}x
            </div>
            <button
              onClick={() => onSpeedChange(Math.min(2.0, playbackSpeed + 0.25))}
              className="w-6 h-6 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors text-xs"
              title="Speed up"
            >
              +
            </button>
          </div>
        )}
      </div>

      {/* Timeline bar */}
      <div
        ref={barRef}
        className="relative h-6 cursor-pointer group"
        onMouseDown={handleBarMouseDown}
      >
        {/* Difficulty heatmap background */}
        <div className="absolute inset-x-0 top-2 h-2 rounded-full overflow-hidden bg-border">
          {(difficulty || []).map((seg, i) => {
            const left = (seg.start / duration) * 100;
            const width = ((seg.end - seg.start) / duration) * 100;
            return (
              <div
                key={i}
                className="absolute top-0 bottom-0"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  backgroundColor: difficultyColor(seg.score),
                  opacity: 0.3,
                }}
              />
            );
          })}
        </div>

        {/* Loop region highlight */}
        {loopStart !== null && loopEnd !== null && !isDragging && (
          <div
            className="absolute top-0 bottom-0 bg-accent/15 border-x border-accent/40"
            style={{
              left: `${(loopStart / duration) * 100}%`,
              width: `${((loopEnd - loopStart) / duration) * 100}%`,
            }}
          />
        )}

        {/* Drag preview region */}
        {dragPreview && (
          <div
            className="absolute top-0 bottom-0 bg-accent/25 border-x border-accent/60"
            style={{
              left: `${(dragPreview.left / duration) * 100}%`,
              width: `${((dragPreview.right - dragPreview.left) / duration) * 100}%`,
            }}
          />
        )}

        {/* Beat markers */}
        {(beats || []).map((beat, i) => {
          const left = (beat.timestamp / duration) * 100;
          const isActive = i === activeBeatIndex;
          return (
            <div
              key={i}
              className={`absolute top-0 bottom-0 cursor-pointer transition-colors ${
                isActive
                  ? "bg-accent w-[2px] shadow-[0_0_6px_rgba(0,212,255,0.6)]"
                  : "w-px bg-text-secondary/40 hover:bg-accent"
              }`}
              style={{ left: `${left}%` }}
              onClick={(e) => {
                e.stopPropagation();
                onBeatClick(beat.timestamp);
              }}
            />
          );
        })}

        {/* Playhead */}
        <div
          className="absolute top-1 w-0.5 h-4 bg-accent rounded-full shadow-[0_0_8px_rgba(0,212,255,0.5)] transition-[left] duration-75"
          style={{ left: `${progress * 100}%` }}
        />
      </div>
    </div>
  );
}
