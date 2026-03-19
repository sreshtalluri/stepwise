"use client";

import { SPEED_RAMP } from "@/lib/constants";

interface SpeedControlProps {
  speed: number;
  loopIteration: number;
  onSpeedChange: (speed: number) => void;
}

export function SpeedControl({
  speed,
  loopIteration,
  onSpeedChange,
}: SpeedControlProps) {
  const isRamping = loopIteration > 0;

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => onSpeedChange(Math.max(0.25, speed - 0.25))}
        className="w-6 h-6 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors text-xs"
      >
        -
      </button>
      <div
        className={`
          text-xs font-mono px-2 py-1 rounded-button border
          ${
            isRamping
              ? "speed-pulse text-accent border-accent"
              : "text-text-secondary border-border"
          }
        `}
      >
        {speed.toFixed(2)}x
      </div>
      <button
        onClick={() =>
          onSpeedChange(Math.min(SPEED_RAMP.maxSpeed, speed + 0.25))
        }
        className="w-6 h-6 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors text-xs"
      >
        +
      </button>
    </div>
  );
}
