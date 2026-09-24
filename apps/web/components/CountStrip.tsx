"use client";

import { useEffect, useRef, useState } from "react";
import type { CountGrid } from "../../../packages/navigation/src/core";
import { stripIndex, stripPosition } from "../lib/flow";

/**
 * The lesson's count strip (DESIGN.md §7 tier 2) on any clock: eight numerals,
 * the active one larger and in ink, a hairline tick under each and one accent
 * dot sliding along. Weight and size carry the state; no box, no second colour.
 *
 * Runs its own rAF and only re-renders when the active count changes, so the
 * page around it does not re-render every frame. The dot is moved through a
 * ref. `still` (reduced motion) freezes the dot on the count instead of
 * sliding it between counts.
 */
export default function CountStrip({
  grid,
  time,
  still = false,
}: {
  grid: CountGrid;
  /** Current time on the grid's timeline, in seconds. */
  time: () => number;
  still?: boolean;
}) {
  const [active, setActive] = useState(-1);
  const dot = useRef<HTMLElement>(null);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const t = time();
      const i = stripIndex(grid, t);
      setActive((prev) => (prev === i ? prev : i));
      if (dot.current) {
        const x = still ? (Math.max(0, i) + 0.5) / 8 : stripPosition(grid, t);
        dot.current.style.left = `${x * 100}%`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [grid, time, still]);

  return (
    <div className="count-strip" aria-hidden="true">
      <div className="counts">
        {[1, 2, 3, 4, 5, 6, 7, 8].map((n, i) => (
          <span key={n} className={i === active ? "on" : undefined}>
            {n}
          </span>
        ))}
      </div>
      <div className="ticks">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <i key={i} />
        ))}
        <b ref={dot} />
      </div>
    </div>
  );
}
