"use client";

interface LoopControlsProps {
  loopStart: number | null;
  loopEnd: number | null;
  onClearLoop: () => void;
  duration: number;
}

export function LoopControls({
  loopStart,
  loopEnd,
  onClearLoop,
  duration,
}: LoopControlsProps) {
  if (loopStart === null || loopEnd === null) return null;

  const formatTime = (t: number) => {
    const secs = Math.floor(t % 60);
    const ms = Math.floor((t % 1) * 100);
    return `${secs}.${ms.toString().padStart(2, "0")}s`;
  };

  return (
    <div className="flex items-center gap-2 text-xs text-text-secondary font-mono">
      <span className="text-accent">Loop:</span>
      <span>
        {formatTime(loopStart)} - {formatTime(loopEnd)}
      </span>
      <button
        onClick={onClearLoop}
        className="text-text-secondary hover:text-error transition-colors"
        title="Clear loop"
      >
        &times;
      </button>
    </div>
  );
}
