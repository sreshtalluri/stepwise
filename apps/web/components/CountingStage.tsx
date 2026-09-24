"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CountGrid } from "../../../packages/navigation/src/core";
import CountStrip from "./CountStrip";
import StageFigure from "./StageFigure";
import { marketing } from "../lib/copy";
import { prefersReducedMotion } from "../lib/reveal";

/**
 * The landing hero's stage: the count strip ticking over a body, so the page
 * teaches the 8-count before anyone uploads (flow redesign, direction B).
 *
 * Deliberately NOT a real clip. No cleared demo clip exists (app/page.tsx),
 * the testing clips are `rights: untested`, and the repo's fixture video is a
 * colour-bar test card. So it is a silent abstract loop: the placeholder
 * figure dips on every count and sways once per eight. The label says what it
 * is. Loud motion is allowed here and nowhere in the app (DESIGN.md §7e);
 * under reduced motion the figure stands still on count 1.
 */
const BPM = 112;
const SPC = 60 / BPM;
const GRID: CountGrid = { countOneS: 0, secondsPerCount: SPC, countTotal: 1e6 };

export default function CountingStage() {
  // Read after mount so the server render and the first client render agree.
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(prefersReducedMotion()), []);
  const t0 = useRef(0);
  const [pose, setPose] = useState({ azimuth: -20, dip: 0 });
  const time = useCallback(() => (reduced ? 0 : (performance.now() - t0.current) / 1000), [reduced]);

  useEffect(() => {
    if (reduced) return;
    t0.current = performance.now();
    let raf = 0;
    const tick = () => {
      const t = time();
      const phase = (t / SPC) % 1; // 0 on the count
      setPose({
        azimuth: -20 + 32 * Math.sin((2 * Math.PI * t) / (8 * SPC)),
        dip: Math.exp(-phase * 6) * 7,
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reduced, time]);

  return (
    <div className="counting">
      <div className="stage counting-stage">
        <span className="stage-label">{marketing.paste.stageLabel}</span>
        <div style={{ position: "absolute", inset: 0, transform: `translateY(${pose.dip}px)` }}>
          <StageFigure azimuth={pose.azimuth} height={200} />
        </div>
      </div>
      <CountStrip grid={GRID} time={time} still={reduced} />
    </div>
  );
}
