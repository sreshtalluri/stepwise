"use client";

import { useCallback, useRef, MouseEvent } from "react";
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
  playbackSpeed: number;
  loopIteration: number;
}

function difficultyColor(score: number): string {
  if (score < 0.4) return "#44ff88";
  if (score < 0.7) return "#ffdd44";
  return "#ff4444";
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
  playbackSpeed,
  loopIteration,
}: TimelineProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const progress = totalFrames > 0 ? currentFrame / (totalFrames - 1) : 0;
  const currentTime = duration * progress;

  const handleBarClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!barRef.current) return;
      const rect = barRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const frame = Math.round(x * (totalFrames - 1));
      onSeek(Math.max(0, Math.min(frame, totalFrames - 1)));
    },
    [totalFrames, onSeek]
  );

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
        {/* Play/Pause */}
        <button
          onClick={onTogglePlay}
          className="w-8 h-8 flex items-center justify-center rounded-button text-accent hover:bg-accent-glow transition-colors"
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

        {/* Time display */}
        <span className="text-text-secondary text-xs font-mono min-w-[80px] tabular-nums">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Loop indicator */}
        {loopStart !== null && loopEnd !== null && (
          <button
            onClick={onClearLoop}
            className="text-xs text-accent bg-accent-glow px-2 py-1 rounded-button hover:brightness-110 transition-all"
          >
            Loop x{loopIteration + 1} &times;
          </button>
        )}

        {/* Speed badge */}
        <div
          className={`
            text-xs font-mono px-2 py-1 rounded-button border border-border
            ${loopIteration > 0 ? "speed-pulse text-accent border-accent" : "text-text-secondary"}
          `}
        >
          {playbackSpeed.toFixed(1)}x
        </div>
      </div>

      {/* Timeline bar */}
      <div
        ref={barRef}
        className="relative h-6 cursor-pointer group"
        onClick={handleBarClick}
      >
        {/* Difficulty heatmap background */}
        <div className="absolute inset-x-0 top-2 h-2 rounded-full overflow-hidden bg-border">
          {difficulty.map((seg, i) => {
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
        {loopStart !== null && loopEnd !== null && (
          <div
            className="absolute top-0 bottom-0 bg-accent/15 border-x border-accent/40"
            style={{
              left: `${(loopStart / duration) * 100}%`,
              width: `${((loopEnd - loopStart) / duration) * 100}%`,
            }}
          />
        )}

        {/* Beat markers */}
        {beats.map((beat, i) => {
          const left = (beat.timestamp / duration) * 100;
          return (
            <div
              key={i}
              className="absolute top-0 bottom-0 w-px bg-text-secondary/40 hover:bg-accent cursor-pointer transition-colors"
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
