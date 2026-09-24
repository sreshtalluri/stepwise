"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import CountStrip from "./CountStrip";
import SkeletonOverlay from "./SkeletonOverlay";
import { processing as copy } from "../lib/copy";
import {
  eightAt,
  eightSpan,
  eightTimes,
  eightTotal,
  flowSteps,
  gridFromCounts,
  handoffHref,
  perMinute,
  type Step,
} from "../lib/flow";
import { localClipUrl, timeRemaining, useJobStatus, type JobStatus } from "../lib/jobStatus";
import { prefersReducedMotion } from "../lib/reveal";
import type { CountGrid } from "../../../packages/navigation/src/core";

/**
 * Processing, as a warm-up room: the flow redesign's direction B ("practice
 * while it builds") with direction A's skeleton overlay and per-step results.
 * docs/DESIGN.md §7c: there is no dead time, because the video is already
 * useful.
 *
 * - The clip plays from the first second, with speed, mirror and sound.
 * - A thin progress rail on top; tapping its line opens the four steps, each
 *   with the result it produced (1 dancer, 117 a minute, 3 of 8 built).
 * - The moment `milestones.counts` lands (~20 s after upload, while the GPU
 *   is still starting), the page becomes the lesson's own count strip over
 *   the raw video: Earlier 8 / Loop / Next 8, one "practise at half speed"
 *   button, one tip at a time.
 * - After the detection pass, the detector's own 2D skeleton is drawn over
 *   the clip (SkeletonOverlay).
 * - At success, one button into the lesson that keeps the speed and loop.
 *
 * Every line on screen comes from JobStatus or its milestones, never a local
 * guess. No 3D is shown before the lesson exists: a half-built body reads as
 * a broken one (§7c), and a placeholder figure here would claim a body we do
 * not have yet.
 */

const SPEEDS = [1, 0.5, 0.75];
const TIP_MS = 9000;

type Milestones = NonNullable<JobStatus["milestones"]>;

export default function ProcessingScreen({ jobId }: { jobId: string }) {
  const feed = useJobStatus(jobId);
  const status = feed.kind === "ok" ? feed.status : null;
  const done = status?.state === "succeeded";

  // Milestones only ride on live documents, so keep the latest of each: the
  // counts are still what the learner is practising when "succeeded" arrives.
  const [milestones, setMilestones] = useState<Milestones>({});
  const incoming = status?.milestones;
  useEffect(() => {
    if (incoming) setMilestones((prev) => ({ ...prev, ...incoming }));
  }, [incoming]);

  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [duration, setDuration] = useState(0);
  const grid = useMemo(
    () => (milestones.counts && duration > 0 ? gridFromCounts(milestones.counts, duration) : null),
    [milestones.counts, duration],
  );

  if (status?.state === "failed" && status.error) {
    return (
      <main className="wrap app-screen">
        <h1 className="app-title">{copy.failedTitle}</h1>
        <p className="muted" role="alert">
          {status.error.message}
        </p>
        {status.error.retryable ? (
          <Link href="/upload" className="btn" style={{ marginTop: 20 }}>
            {copy.retry}
          </Link>
        ) : null}
      </main>
    );
  }

  const steps = flowSteps(status ? { ...status, milestones } : null, grid);

  return (
    <main className="proc">
      <Rail feed={feed} steps={steps} />
      <div className="wrap proc-grid">
        <Practice
          jobId={jobId}
          video={video}
          setVideo={setVideo}
          onDuration={setDuration}
          grid={grid}
          milestones={milestones}
          done={done}
        />
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------- rail

function Rail({ feed, steps }: { feed: ReturnType<typeof useJobStatus>; steps: Step[] }) {
  const status = feed.kind === "ok" ? feed.status : null;
  const remaining = feed.kind === "ok" ? timeRemaining(feed.status, feed.elapsedMs) : null;
  const progress = status?.state === "succeeded" ? 1 : (status?.progress ?? 0);
  const message =
    status?.state === "succeeded"
      ? copy.steps.ready
      : status?.stage_message || copy.waiting;

  return (
    <div className="rail">
      <div
        className="rail-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label={message}
      >
        <i style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="wrap rail-row">
        <details className="rail-steps">
          <summary aria-live="polite">
            <b>{message}</b>
            {remaining && status?.state === "processing" ? <span className="meta"> {remaining}</span> : null}
          </summary>
          <ol>
            {steps.map((s) => (
              <li key={s.key} className={`step-${s.state}`}>
                <b>{s.label}</b>
                <span>{s.note}</span>
              </li>
            ))}
            <li className="step-close meta">{copy.closeable}</li>
          </ol>
        </details>
        <CopyLink />
      </div>
      {feed.kind === "unreachable" && <p className="wrap meta">{copy.unreachable}</p>}
    </div>
  );
}

function CopyLink() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-sm btn-ghost"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          // Clipboard blocked: the address bar still has it.
          setCopied(false);
        }
      }}
    >
      {copied ? copy.copied : copy.copyLink}
    </button>
  );
}

// ------------------------------------------------------------------ practice

function Practice({
  jobId,
  video,
  setVideo,
  onDuration,
  grid,
  milestones,
  done,
}: {
  jobId: string;
  video: HTMLVideoElement | null;
  setVideo: (v: HTMLVideoElement | null) => void;
  onDuration: (s: number) => void;
  grid: CountGrid | null;
  milestones: Milestones;
  done: boolean;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const [mirror, setMirror] = useState(false);
  const [muted, setMuted] = useState(true);
  const [paused, setPaused] = useState(false);
  const [loopN, setLoopN] = useState(0); // 0 = off, else the 1-based eight-count
  const [practised, setPractised] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setSrc(localClipUrl(jobId) ?? `/api/jobs/${encodeURIComponent(jobId)}/video`);
    setReduced(prefersReducedMotion());
  }, [jobId]);

  useEffect(() => {
    if (video) video.playbackRate = speed;
  }, [video, speed, src]);

  const time = useCallback(() => video?.currentTime ?? 0, [video]);
  const eight = useEightAt(grid, time);
  const duration = video?.duration && Number.isFinite(video.duration) ? video.duration : 0;

  // The loop, on the raw video: wrap at the end of the eight, count-exact.
  useEffect(() => {
    if (!video || !grid || !loopN) return;
    const [a, b] = eightTimes(grid, loopN, video.duration || Infinity);
    let raf = 0;
    const tick = () => {
      if (video.currentTime >= b - 0.02 || video.currentTime < a - 0.25) video.currentTime = a;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [video, grid, loopN]);

  const setLoop = useCallback(
    (n: number) => {
      setLoopN(n);
      if (n && video && grid) video.currentTime = eightTimes(grid, n, duration || Infinity)[0];
    },
    [video, grid, duration],
  );

  const total = grid ? eightTotal(grid) : 0;
  const shown = loopN || eight;
  const nextSpeed = () => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]);
  const togglePlay = useCallback(() => {
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, [video]);

  // DESIGN.md §8 keys: M mirror, L loop, S speed, space play/pause.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === "m") setMirror((m) => !m);
      else if (k === "s") setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length]);
      else if (k === "l" && grid) setLoop(loopN ? 0 : eight);
      else if (k === " ") {
        e.preventDefault();
        togglePlay();
      } else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [grid, loopN, eight, setLoop, togglePlay]);

  const counts = milestones.counts;
  const title = done ? copy.readyTitle : grid ? copy.countsTitle : copy.title;
  const sub = done ? copy.readySubtitle : grid ? copy.countsSubtitle : copy.subtitle;
  const span = grid ? eightSpan(grid, shown) : null;

  return (
    <>
      <div
        className="stage proc-video"
        onClick={togglePlay}
        role="button"
        tabIndex={-1}
        aria-label={copy.videoLabel}
      >
        <span className="stage-label proc-label">{copy.videoLabel}</span>
        <div className="proc-mirror" style={{ transform: mirror ? "scaleX(-1)" : undefined }}>
          {src && (
            <video
              ref={setVideo}
              src={src}
              autoPlay
              muted={muted}
              playsInline
              loop={!loopN}
              onLoadedMetadata={(e) => onDuration(e.currentTarget.duration)}
              onPlay={() => setPaused(false)}
              onPause={() => setPaused(true)}
            />
          )}
          <SkeletonOverlay jobId={jobId} video={video} available={milestones.dancers != null} />
        </div>
        {paused && <span className="stage-label proc-paused">{copy.paused}</span>}
      </div>

      <div className="proc-panel">
        <h1 className="proc-title">{title}</h1>
        <p className="proc-sub">{sub}</p>

        <div className="proc-counts">
          <div className="proc-part">
            <b>{span ? copy.part(span.startCount, span.endCount) : copy.part(1, 8)}</b>
            {counts && (
              <span className="meta">
                {counts.confidence < 0.5 ? copy.tempoWeak(perMinute(counts)) : copy.tempo(perMinute(counts))}
              </span>
            )}
          </div>
          {grid ? (
            <div className="appear">
              <CountStrip grid={grid} time={time} still={reduced} />
            </div>
          ) : (
            <div className="listening">
              <i />
              {copy.listening}
            </div>
          )}
        </div>

        <div className="tools proc-tools">
          <button type="button" className="tool" disabled={!grid} onClick={() => setLoop(Math.max(1, shown - 1))}>
            {copy.earlier}
          </button>
          <button
            type="button"
            className="tool"
            disabled={!grid}
            aria-pressed={loopN > 0}
            onClick={() => setLoop(loopN ? 0 : eight)}
          >
            {loopN && span ? copy.loopEight(span.startCount, span.endCount) : copy.loopOff}
          </button>
          <button type="button" className="tool" disabled={!grid} onClick={() => setLoop(Math.min(total, shown + 1))}>
            {copy.next}
          </button>
          <button type="button" className="tool" onClick={nextSpeed}>
            {copy.speed(speed)}
          </button>
          <button type="button" className="tool" aria-pressed={mirror} onClick={() => setMirror((m) => !m)}>
            {mirror ? copy.mirrorOn : copy.mirrorOff}
          </button>
          <button type="button" className="tool" aria-pressed={!muted} onClick={() => setMuted((m) => !m)}>
            {muted ? copy.soundOff : copy.soundOn}
          </button>
        </div>

        {done ? (
          <Link
            href={handoffHref(jobId, speed, loopN && grid ? eightSpan(grid, loopN) : null)}
            className="btn btn-lg proc-go appear"
          >
            {copy.open}
          </Link>
        ) : grid && !practised && !loopN ? (
          <button
            type="button"
            className="btn btn-lg proc-go appear"
            onClick={() => {
              setSpeed(0.5);
              setLoop(1);
              setPractised(true);
            }}
          >
            {copy.practice}
          </button>
        ) : null}

        {!done && <Tip rotating={!!grid} />}
      </div>
    </>
  );
}

/** One tip at a time. Before the counts, the one thing worth knowing: you can leave. */
function Tip({ rotating }: { rotating: boolean }) {
  const [i, setI] = useState(-1);
  useEffect(() => {
    if (!rotating) return;
    setI(0);
    const id = setInterval(() => setI((n) => (n + 1) % copy.tips.length), TIP_MS);
    return () => clearInterval(id);
  }, [rotating]);
  const text = rotating && i >= 0 ? copy.tips[i] : copy.closeable;
  return (
    <div className="proc-tip">
      <b>{copy.tipLabel}</b>
      <span key={text} className="appear">
        {text}
      </span>
    </div>
  );
}

/** The eight-count under the playhead, re-rendering only when it changes. */
function useEightAt(grid: CountGrid | null, time: () => number): number {
  const [n, setN] = useState(1);
  useEffect(() => {
    if (!grid) return;
    let raf = 0;
    const tick = () => {
      const next = eightAt(grid, time());
      setN((prev) => (prev === next ? prev : next));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [grid, time]);
  return n;
}
