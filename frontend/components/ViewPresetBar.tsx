"use client";

import { ViewPreset, DetailLayer } from "@/lib/types";

interface ViewPresetBarProps {
  activePreset: ViewPreset;
  activeLayers: Set<DetailLayer>;
  onSelectPreset: (preset: ViewPreset) => void;
  onToggleLayer: (layer: DetailLayer) => void;
  xrayMode?: boolean;
  onXrayToggle?: () => void;
  hasMannequinData?: boolean;
}

const PRESET_BUTTONS: { id: ViewPreset; label: string }[] = [
  { id: 1, label: "Front" },
  { id: 2, label: "Mirror" },
  { id: 3, label: "Side by Side" },
  { id: 4, label: "Front+Back" },
  { id: 5, label: "Ghost" },
  { id: 6, label: "Video+PiP" },
  { id: 7, label: "Freeze" },
  { id: 8, label: "Split Mirror" },
];

const LAYER_BUTTONS: { id: DetailLayer; label: string }[] = [
  { id: "hands", label: "Hands" },
  { id: "footwork", label: "Footwork" },
];

export function ViewPresetBar({
  activePreset,
  activeLayers,
  onSelectPreset,
  onToggleLayer,
  xrayMode = false,
  onXrayToggle,
  hasMannequinData = false,
}: ViewPresetBarProps) {
  return (
    <div
      className="flex items-center gap-1 px-4 py-2 overflow-x-auto [scrollbar-width:none] [-webkit-overflow-scrolling:touch] [&::-webkit-scrollbar]:hidden"
      style={{
        backgroundColor: "#141414",
        borderBottom: "1px solid #222222",
      }}
    >
      {/* Preset buttons */}
      <div className="flex items-center gap-1">
        {PRESET_BUTTONS.map(({ id, label }) => {
          const isActive = activePreset === id;
          return (
            <button
              key={id}
              onClick={() => onSelectPreset(id)}
              className="px-3 py-1.5 rounded-button text-sm font-medium font-body transition-all duration-150 whitespace-nowrap"
              style={
                isActive
                  ? {
                      backgroundColor: "#00d4ff",
                      color: "#0a0a0a",
                      boxShadow: "0 0 12px rgba(0,212,255,0.3)",
                    }
                  : {
                      backgroundColor: "transparent",
                      color: "#888888",
                    }
              }
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = "#1a1a1a";
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = "transparent";
                }
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Divider */}
      <div
        className="h-6 mx-2 flex-shrink-0"
        style={{ width: "1px", backgroundColor: "#222222" }}
      />

      {/* Detail layers */}
      <div className="flex items-center gap-1">
        {LAYER_BUTTONS.map(({ id, label }) => {
          const isActive = activeLayers.has(id);
          return (
            <button
              key={id}
              onClick={() => onToggleLayer(id)}
              className="px-3 py-1.5 rounded-button text-sm font-medium font-body transition-all duration-150 whitespace-nowrap"
              style={
                isActive
                  ? {
                      backgroundColor: "#00d4ff",
                      color: "#0a0a0a",
                      boxShadow: "0 0 12px rgba(0,212,255,0.3)",
                    }
                  : {
                      backgroundColor: "transparent",
                      color: "#888888",
                    }
              }
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = "#1a1a1a";
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = "transparent";
                }
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* X-Ray toggle — only shown when mannequin data is available */}
      {hasMannequinData && (
        <>
          <div
            className="h-6 mx-2 flex-shrink-0"
            style={{ width: "1px", backgroundColor: "#222222" }}
          />
          <button
            onClick={onXrayToggle}
            className="px-3 py-1.5 rounded-button text-sm font-medium font-body transition-all duration-150 whitespace-nowrap"
            style={
              xrayMode
                ? {
                    backgroundColor: "#00d4ff",
                    color: "#0a0a0a",
                    boxShadow: "0 0 12px rgba(0,212,255,0.3)",
                  }
                : {
                    backgroundColor: "transparent",
                    color: "#888888",
                  }
            }
            onMouseEnter={(e) => {
              if (!xrayMode) {
                e.currentTarget.style.backgroundColor = "#1a1a1a";
              }
            }}
            onMouseLeave={(e) => {
              if (!xrayMode) {
                e.currentTarget.style.backgroundColor = "transparent";
              }
            }}
            title="Toggle X-ray skeleton view (X)"
            role="switch"
            aria-checked={xrayMode}
            aria-label="Toggle X-ray skeleton view"
          >
            X-Ray
          </button>
        </>
      )}
    </div>
  );
}
