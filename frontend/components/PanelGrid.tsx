"use client";

import { ReactNode } from "react";

interface PanelGridProps {
  panels: { key: string; label: string; content: ReactNode }[];
  visibleKeys?: Set<string>;
}

export function PanelGrid({ panels, visibleKeys }: PanelGridProps) {
  // If visibleKeys is provided, only show those panels in the layout
  // but keep all panels mounted (hidden ones use display:none to preserve WebGL contexts).
  const visiblePanels = visibleKeys
    ? panels.filter((p) => visibleKeys.has(p.key))
    : panels;
  const count = visiblePanels.length;

  // Grid classes based on visible panel count
  const gridClass = (() => {
    switch (count) {
      case 1:
        return "grid-cols-1";
      case 2:
        return "grid-cols-1 md:grid-cols-2";
      case 3:
        return "grid-cols-1 md:grid-cols-2";
      case 4:
        return "grid-cols-1 md:grid-cols-2";
      default:
        return "grid-cols-1 md:grid-cols-2";
    }
  })();

  // Track visible panel index for col-span logic
  let visibleIndex = 0;

  return (
    <div className={`grid ${gridClass} gap-1 h-full transition-all duration-200 ease-in-out`}>
      {panels.map((panel) => {
        const isVisible = !visibleKeys || visibleKeys.has(panel.key);
        const idx = isVisible ? visibleIndex++ : -1;

        return (
          <div
            key={panel.key}
            className={`
              relative bg-surface border border-border rounded-panel overflow-hidden
              transition-all duration-200 ease-in-out
              ${isVisible && count === 3 && idx === 2 ? "md:col-span-2" : ""}
            `}
            style={isVisible ? undefined : { display: "none" }}
          >
            {/* Panel label */}
            <div className="absolute top-2 left-3 z-10 text-xs text-text-secondary font-medium uppercase tracking-wider bg-surface/80 px-2 py-1 rounded-button font-mono">
              {panel.label}
            </div>
            {panel.content}
          </div>
        );
      })}
    </div>
  );
}
