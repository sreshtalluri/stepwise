"use client";

interface ProcessingStatusProps {
  step: string;
}

export function ProcessingStatus({ step }: ProcessingStatusProps) {
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
      <p className="text-text-secondary text-sm">
        This usually takes a few seconds
      </p>

      {/* Progress dots */}
      <div className="flex gap-2 mt-6">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-2 h-2 rounded-full bg-accent"
            style={{
              opacity: 0.3,
              animation: `pulse-glow 1.2s ease-in-out ${i * 0.3}s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
