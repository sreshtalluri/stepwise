"use client";

import { CameraAngle, DetailLayer } from "@/lib/types";

interface CameraAngleBarProps {
  activeAngles: Set<CameraAngle>;
  activeLayers: Set<DetailLayer>;
  onToggleAngle: (angle: CameraAngle) => void;
  onToggleLayer: (layer: DetailLayer) => void;
}

const ANGLE_BUTTONS: { id: CameraAngle; label: string }[] = [
  { id: "video", label: "Video" },
  { id: "front", label: "Front" },
  { id: "back", label: "Back" },
  { id: "mirror", label: "Mirror" },
  { id: "ghost", label: "Ghost" },
];

const LAYER_BUTTONS: { id: DetailLayer; label: string }[] = [
  { id: "hands", label: "Hands" },
  { id: "footwork", label: "Footwork" },
];

export function CameraAngleBar({
  activeAngles,
  activeLayers,
  onToggleAngle,
  onToggleLayer,
}: CameraAngleBarProps) {
  return (
    <div className="flex items-center gap-1 px-4 py-2 bg-surface border-b border-border overflow-x-auto [scrollbar-width:none] [-webkit-overflow-scrolling:touch] [&::-webkit-scrollbar]:hidden">
      {/* Camera angles */}
      <div className="flex items-center gap-1">
        {ANGLE_BUTTONS.map(({ id, label }) => {
          const isActive = activeAngles.has(id);
          return (
            <button
              key={id}
              onClick={() => onToggleAngle(id)}
              className={`
                px-3 py-1.5 rounded-button text-sm font-medium font-body
                transition-all duration-150 whitespace-nowrap
                ${
                  isActive
                    ? "bg-accent text-bg shadow-[0_0_12px_rgba(0,212,255,0.3)]"
                    : "text-text-secondary hover:text-text-primary hover:bg-[#1a1a1a]"
                }
              `}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Divider */}
      <div className="w-px h-6 bg-border mx-2 flex-shrink-0" />

      {/* Detail layers */}
      <div className="flex items-center gap-1">
        {LAYER_BUTTONS.map(({ id, label }) => {
          const isActive = activeLayers.has(id);
          return (
            <button
              key={id}
              onClick={() => onToggleLayer(id)}
              className={`
                px-3 py-1.5 rounded-button text-sm font-medium font-body
                transition-all duration-150 whitespace-nowrap
                ${
                  isActive
                    ? "bg-accent text-bg shadow-[0_0_12px_rgba(0,212,255,0.3)]"
                    : "text-text-secondary hover:text-text-primary hover:bg-[#1a1a1a]"
                }
              `}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
