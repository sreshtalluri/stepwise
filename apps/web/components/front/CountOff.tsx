"use client";

import { useEffect, useRef, useState } from "react";
import { marketing } from "../../lib/copy";
import { TOY_SPEEDS, buildStep, drawFigure } from "../../lib/countoff";
import { prefersReducedMotion } from "../../lib/reveal";
import { useVisible } from "./useVisible";

const copy = marketing.toy;
const SECONDS_PER_COUNT = 0.5; // a fixed, neutral tempo: this is a toy, not a song
const EIGHT = [1, 2, 3, 4, 5, 6, 7, 8];

/**
 * The hero's count-off (A2): a screen-sized numeral calls 1 to 8 while a
 * drawn figure hits each count. Build up, speed and mirror really work on it.
 *
 * Layout rule: the numeral and the figure share one grid cell (.fd-stagev)
 * and NOTHING readable or tappable is ever layered over them; caption, chips
 * and the count row each have their own cell.
 *
 * Motion level 6 is allowed here only (DESIGN.md §9). Reduced motion freezes
 * it on count 1; it also stops while scrolled out of view.
 */
export default function CountOff() {
  const [speed, setSpeed] = useState<number>(1);
  const [build, setBuild] = useState(false);
  const [mirror, setMirror] = useState(false);
  const toy = useRef({ speed: 1, build: false, mirror: false });
  toy.current = { speed, build, mirror };

  const root = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const big = useRef<HTMLElement>(null);
  const row = useRef<HTMLDivElement>(null);
  const visible = useVisible(root);
  const beatRef = useRef(0);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduced = prefersReducedMotion();
    const ink = getComputedStyle(cv).getPropertyValue("--ink").trim() || "#221e1c";
    let lastN = 0;
    let last = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      const t = toy.current;
      if (!reduced) beatRef.current += (Math.min(250, now - last) / 1000 / SECONDS_PER_COUNT) * t.speed;
      last = now;
      const beat = beatRef.current;
      const a = Math.floor(beat);
      const n = (a % 8) + 1;
      if (n !== lastN) {
        // Build up: each time round the eight, a tenth faster, up to 1x.
        if (n === 1 && lastN === 8 && t.build) setSpeed((s) => buildStep(s));
        lastN = n;
        if (big.current) {
          big.current.textContent = String(n);
          if (!reduced) {
            big.current.classList.remove("fd-hit");
            void big.current.offsetWidth;
            big.current.classList.add("fd-hit");
          }
        }
        row.current?.querySelectorAll("i").forEach((c, i) => c.classList.toggle("fd-on", i === n - 1));
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
      const fh = Math.min(h * 0.92, w * 1.5);
      drawFigure(ctx, w / 2, h * 0.98, fh, n, reduced ? 1 : beat - a, { color: ink, width: 3.2, flip: t.mirror });
      // Off screen: one frame drawn, then nothing runs until it scrolls back.
      if (visible) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [visible]);

  return (
    <div className="fd-counter" ref={root}>
      <p className="fd-counter-cap">{copy.caption}</p>
      <div className="fd-toy">
        <button
          type="button"
          className="fd-chip"
          aria-pressed={build}
          onClick={() => {
            setBuild(!build);
            if (!build) setSpeed(0.5);
          }}
        >
          {copy.build}
        </button>
        <button
          type="button"
          className="fd-chip"
          aria-pressed={speed !== 1}
          onClick={() => {
            setBuild(false);
            const i = TOY_SPEEDS.indexOf(speed as (typeof TOY_SPEEDS)[number]);
            setSpeed(TOY_SPEEDS[(i + 1) % TOY_SPEEDS.length]);
          }}
        >
          {copy.speed(speed)}
        </button>
        <button type="button" className="fd-chip" aria-pressed={mirror} onClick={() => setMirror(!mirror)}>
          {mirror ? copy.mirrorOn : copy.mirrorOff}
        </button>
      </div>
      <div className="fd-stagev" aria-hidden="true">
        <div className="fd-big">
          <b ref={big}>1</b>
        </div>
        <canvas ref={canvas} />
      </div>
      <div className="fd-eights" ref={row} aria-hidden="true">
        {EIGHT.map((n) => (
          <i key={n} className={n === 1 ? "fd-on" : undefined}>
            {n}
          </i>
        ))}
      </div>
    </div>
  );
}
