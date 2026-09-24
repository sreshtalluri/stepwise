"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { marketing } from "../../lib/copy";
import { prefersReducedMotion } from "../../lib/reveal";
import { useVisible } from "./useVisible";

const copy = marketing.demo;

export interface DemoClip {
  /** Cleared footage only (the owner's friends, with their say-so). 720p, ~1.5 MB, muted. */
  src: string;
  /** A frame from the clip, shown before it plays and under reduced motion. */
  poster: string;
  /** The finished lesson built from this clip, for "Open this lesson". */
  lessonId: string;
  /** That lesson's counts, as set and checked in the lesson (not the raw proposal). */
  countOneS: number;
  secondsPerCount: number;
}

/**
 * THE ONE PLACE A REAL DEMO CLIP GOES. Set this and the section below becomes
 * the on-video demo: muted, looped, playsinline, playing only while on screen
 * (IntersectionObserver), poster first, the count ticking with the clip.
 *
 * It is null on purpose. No cleared clip exists yet: the testing clips are
 * `rights: untested` (never ship solo-02.mp4 or a fixture test card), so the
 * stage is an honest empty state labelled "Demo clip coming soon".
 * DESIGN.md §7d records this too.
 */
export const DEMO: DemoClip | null = null;

const PLACEHOLDER_SPC = 0.5; // the placeholder's ambient count: a neutral tempo, no music
const EIGHT = [1, 2, 3, 4, 5, 6, 7, 8];

export default function Demo({ clip = DEMO }: { clip?: DemoClip | null }) {
  const stage = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const row = useRef<HTMLDivElement>(null);
  const visible = useVisible(stage, 0.35);
  const [reduced, setReduced] = useState(false);
  const [paused, setPaused] = useState(true);
  const [aspect, setAspect] = useState(0);
  useEffect(() => setReduced(prefersReducedMotion()), []);

  // Plays only while on screen; reduced motion never autoplays.
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (visible && !reduced) {
      v.preload = "auto";
      v.play().catch(() => setPaused(true));
    } else v.pause();
  }, [visible, reduced]);

  // The count row: the clip's own counts when there is a clip, else an ambient tick.
  useEffect(() => {
    if (!visible || (reduced && !clip)) return;
    let raf = 0;
    let lastN = -1;
    const t0 = performance.now();
    const tick = () => {
      let n = 0;
      if (clip) {
        const t = video.current?.currentTime ?? 0;
        const x = (t - clip.countOneS) / clip.secondsPerCount;
        n = t > 0 && x >= 0 ? (Math.floor(x) % 8) + 1 : 0;
      } else n = (Math.floor((performance.now() - t0) / 1000 / PLACEHOLDER_SPC) % 8) + 1;
      if (n !== lastN) {
        lastN = n;
        row.current?.querySelectorAll("i").forEach((c, i) => c.classList.toggle("fd-on", i === n - 1));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible, reduced, clip]);

  return (
    <section className="fd-demo" id="demo">
      <div>
        <h2 className="fd-h2">{copy.heading}</h2>
        <p className="fd-lede">{copy.body}</p>
        {clip && (
          <Link className="fd-btn fd-btn-ghost fd-demo-open" href={`/lesson/${encodeURIComponent(clip.lessonId)}`}>
            {copy.open}
          </Link>
        )}
      </div>
      <div>
        <div
          className={`fd-demo-stage${clip ? "" : " fd-demo-empty"}`}
          ref={stage}
          data-wide={aspect >= 1 ? "" : undefined}
          style={aspect ? ({ ["--ar" as string]: aspect } as React.CSSProperties) : undefined}
        >
          <span className="fd-tag">{copy.onVideo}</span>
          {clip ? (
            <>
              <video
                ref={video}
                src={clip.src}
                poster={clip.poster}
                muted
                playsInline
                loop
                preload="none"
                aria-label={copy.heading}
                onPlay={() => setPaused(false)}
                onPause={() => setPaused(true)}
                onLoadedMetadata={(e) => setAspect(e.currentTarget.videoWidth / (e.currentTarget.videoHeight || 1))}
              />
              {reduced && paused && (
                <button type="button" className="fd-demo-play" onClick={() => void video.current?.play()}>
                  {copy.play}
                </button>
              )}
            </>
          ) : (
            <p className="fd-demo-soon">{copy.placeholder}</p>
          )}
        </div>
        <div className="fd-beat" ref={row} aria-hidden="true">
          {EIGHT.map((n) => (
            <i key={n}>{n}</i>
          ))}
        </div>
      </div>
    </section>
  );
}
