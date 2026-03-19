"use client";

interface ProcessingStatusProps {
  step: string;
  currentStepIndex?: number;
  totalSteps?: number;
}

export function ProcessingStatus({ step, currentStepIndex = 0, totalSteps = 5 }: ProcessingStatusProps) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4">
      {/* Spinner */}
      <div className="relative w-20 h-20 mb-8">
        <div className="absolute inset-0 rounded-full border-2 border-border" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent spin-slow" />
        <div
          className="absolute inset-2 rounded-full border-2 border-transparent border-t-accent spin-slow"
          style={{ animationDirection: "reverse", animationDuration: "1.5s" }}
        />
      </div>

      {/* Step label */}
      <p className="text-text-primary text-xl font-medium mb-2">{step}</p>
      <p className="text-text-secondary text-base">
        This usually takes a few seconds
      </p>

      {/* Step counter */}
      <p className="text-text-secondary text-sm mt-1">
        Step {currentStepIndex + 1} of {totalSteps}
      </p>

      {/* Segmented progress bar */}
      <div className="flex gap-1.5 mt-6 w-64">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
              i < currentStepIndex
                ? "bg-accent"
                : i === currentStepIndex
                ? "bg-accent animate-pulse"
                : "bg-border"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
