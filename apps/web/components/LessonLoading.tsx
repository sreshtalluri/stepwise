"use client";

import { useEffect, useRef } from "react";
import { lesson as lessonCopy } from "../lib/copy";
import { drawFigure } from "../lib/countoff";
import { prefersReducedMotion } from "../lib/reveal";

const SECONDS_PER_COUNT = 0.5; // a neutral tempo: this is a wait, not the song

/**
 * The lesson's loading screen: the landing's count-off (A2), full-bleed, while
 * the lesson document downloads. It claims nothing it cannot see: there is no
 * percentage, because a gzipped response's Content-Length does not match the
 * bytes the stream hands us, so the bar is indeterminate. Reduced motion shows
 * a still figure on count 1.
 */
export default function LessonLoading() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const big = useRef<HTMLElement>(null);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduced = prefersReducedMotion();
    const ink = getComputedStyle(cv).getPropertyValue("--ink").trim() || "#221e1c";
    let beat = 0;
    let lastN = 0;
    let last = performance.now();
    let raf = 0;
    const frame = (now: number) => {
      if (!reduced) beat += Math.min(250, now - last) / 1000 / SECONDS_PER_COUNT;
      last = now;
      const a = Math.floor(beat);
      const n = (a % 8) + 1;
      if (n !== lastN && big.current) {
        lastN = n;
        big.current.textContent = String(n);
        if (!reduced) {
          big.current.classList.remove("fd-hit");
          void big.current.offsetWidth;
          big.current.classList.add("fd-hit");
        }
      }
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      drawFigure(ctx, w / 2, h * 0.98, Math.min(h * 0.92, w * 1.5), n, reduced ? 1 : beat - a, {
        color: ink,
        width: 3.2,
        flip: false,
      });
      if (!reduced) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <main className="ll" aria-busy="true">
      <div className="fd-stagev ll-stage" aria-hidden="true">
        <div className="fd-big">
          <b ref={big}>1</b>
        </div>
        <canvas ref={canvas} />
      </div>
      <div className="ll-text">
        <p className="ll-title" role="status" aria-live="polite">
          {lessonCopy.load.loading}
        </p>
        <div className="ll-bar" aria-hidden="true">
          <span />
        </div>
        <p className="ll-note">{lessonCopy.load.loadingNote}</p>
      </div>
    </main>
  );
}
