"use client";

import { ReactNode } from "react";

interface PanelGridProps {
  panels: { key: string; label: string; content: ReactNode }[];
}

export function PanelGrid({ panels }: PanelGridProps) {
  const count = panels.length;

  // Grid classes based on panel count
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

  return (
    <div className={`grid ${gridClass} gap-1 h-full`}>
      {panels.map((panel, i) => (
        <div
          key={panel.key}
          className={`
            relative bg-surface border border-border rounded-panel overflow-hidden
            ${count === 3 && i === 2 ? "md:col-span-2" : ""}
          `}
        >
          {/* Panel label */}
          <div className="absolute top-2 left-3 z-10 text-xs text-text-secondary font-medium uppercase tracking-wider bg-surface/80 px-2 py-1 rounded-button">
            {panel.label}
          </div>
          {panel.content}
        </div>
      ))}
    </div>
  );
}
