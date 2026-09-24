"use client";

import { useEffect, useRef } from "react";
import { lesson as lessonCopy } from "../lib/copy";
import { drawFigure } from "../lib/countoff";
import { prefersReducedMotion } from "../lib/reveal";

const SECONDS_PER_COUNT = 0.6; // calmer than the landing's toy: this is a wait, not the song
const FIG_W = 120;
const FIG_H = 160;
const EIGHT = [1, 2, 3, 4, 5, 6, 7, 8];

/**
 * The lesson's loading screen, "Quiet dancer" (owner's pick): the landing's
 * drawn figure, small and thin, gliding between its eight poses, with eight
 * dots that light up on the count and one line of text. No percentage: nothing
 * here can honestly measure the download. Reduced motion shows a still figure.
 */
export default function LessonLoading() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const dots = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = FIG_W * dpr;
    cv.height = FIG_H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const reduced = prefersReducedMotion();
    const ink = getComputedStyle(cv).getPropertyValue("--ink").trim() || "#221e1c";
    const start = performance.now();
    let lastN = 0;
    let raf = 0;
    const frame = (now: number) => {
      const beat = reduced ? 0 : (now - start) / 1000 / SECONDS_PER_COUNT;
      const a = Math.floor(beat);
      const n = (a % 8) + 1;
      if (n !== lastN) {
        lastN = n;
        dots.current?.querySelectorAll("i").forEach((d, i) => d.classList.toggle("ll-on", i === n - 1));
      }
      ctx.clearRect(0, 0, FIG_W, FIG_H);
      drawFigure(ctx, FIG_W / 2, FIG_H - 4, FIG_H * 0.9, n, reduced ? 1 : beat - a, {
        color: ink,
        flip: false,
        soft: true,
      });
      if (!reduced) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <main className="ll" aria-busy="true">
      <div className="ll-quiet">
        <canvas ref={canvas} style={{ width: FIG_W, height: FIG_H }} aria-hidden="true" />
        <div className="ll-dots" ref={dots} aria-hidden="true">
          {EIGHT.map((n) => (
            <i key={n} className={n === 1 ? "ll-on" : undefined} />
          ))}
        </div>
        <p className="ll-title" role="status" aria-live="polite">
          {lessonCopy.load.loading}
        </p>
      </div>
    </main>
  );
}
