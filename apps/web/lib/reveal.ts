"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The reveal orbit — docs/DESIGN.md §7f.
 *
 * When processing completes the camera performs one slow orbit around the
 * figure (~2.5s, eased, front → side → front) and then settles at the camera
 * view. It teaches the core interaction without a tooltip, it is the
 * screenshot people take, and it fires *once per lesson, never again*.
 *
 * This module owns the timing and the once-per-lesson bookkeeping only. It
 * emits an azimuth in degrees; whatever renders the figure consumes it. That
 * keeps it usable by the placeholder stage here and by the real R3F viewer
 * (W5) without either owning the other.
 */

export const REVEAL_DURATION_MS = 2500;
const STORAGE_PREFIX = "stepwise.reveal.";

/** Eased 0..1. Slow out of the front, quick through the back, slow back in. */
export function easeInOutCubic(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return c < 0.5 ? 4 * c * c * c : 1 - Math.pow(-2 * c + 2, 3) / 2;
}

/** Azimuth in degrees at elapsed `ms` — one full orbit, settling back at 0. */
export function revealAzimuth(ms: number, duration = REVEAL_DURATION_MS): number {
  if (ms >= duration) return 0;
  return easeInOutCubic(ms / duration) * 360;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Has this lesson already had its one reveal? */
export function revealAlreadyPlayed(lessonId: string): boolean {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + lessonId) !== null;
  } catch {
    // Private mode or storage disabled: treat as "already played" so we never
    // replay the orbit on every visit. A missed reveal beats a repeated one.
    return true;
  }
}

export function markRevealPlayed(lessonId: string): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + lessonId, String(Date.now()));
  } catch {
    /* nothing to do — see revealAlreadyPlayed */
  }
}

/**
 * Returns the reveal azimuth in degrees while the orbit is running, or null
 * when it is not (before `armed`, after it finishes, on a repeat visit, or
 * under prefers-reduced-motion). Null means "you are in control of the
 * camera" — the consumer should fall back to the user's own orbit.
 */
export function useRevealOrbit(lessonId: string, armed: boolean): number | null {
  const [azimuth, setAzimuth] = useState<number | null>(null);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (!armed) return;
    if (prefersReducedMotion()) return; // §7f: never under reduced motion
    if (revealAlreadyPlayed(lessonId)) return;

    markRevealPlayed(lessonId); // claim it before animating, so a mid-orbit
    // reload does not replay it
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed >= REVEAL_DURATION_MS) {
        setAzimuth(null);
        return;
      }
      setAzimuth(revealAzimuth(elapsed));
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);

    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      setAzimuth(null);
    };
  }, [lessonId, armed]);

  return azimuth;
}
