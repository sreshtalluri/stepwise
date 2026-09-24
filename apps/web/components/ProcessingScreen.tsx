"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import SkeletonOverlay from "./SkeletonOverlay";
import StateScreen, { StateNote } from "./StateScreen";
import { processing as copy } from "../lib/copy";
import { failedBody, flowSteps, handoffHref, type Step } from "../lib/flow";
import { localClipUrl, timeRemaining, useJobStatus, type JobStatus } from "../lib/jobStatus";
import { prefersReducedMotion } from "../lib/reveal";
import { track } from "../lib/analytics";

/**
 * Processing, A2 "Count off" with the owner's change of 2026-09-23: wait for
 * the whole analysis, then hand off to the full lesson.
 *
 * - The clip plays from the first second, muted, with speed, mirror and sound.
 * - The rail and the steps say only what JobStatus says: its stage_message,
 *   progress, and the milestones that are true (dancers found, frames built).
 * - Once the detection pass lands, the detector's own 2D skeleton is drawn on
 *   the clip (SkeletonOverlay).
 * - The big numeral is a heartbeat, ticking at a steady 60 a minute that is
 *   NOT the song, and the page says so. It stops on 8 when the lesson is ready.
 * - At success, one button: "Open the lesson", carrying the speed.
 *
 * No counts on this page. The early `milestones.counts` were often off the
 * beat and put count 1 on the intro before the dancer starts, so the early
 * 8-count practice that used to live here is gone. The backend still sends
 * the milestone; it is ignored here. Future: bring the practice back once
 * count 1 is reliable.
 */

const SPEEDS = [1, 0.75, 0.5];
const HEARTBEAT_MS = 1000;

type Milestones = NonNullable<JobStatus["milestones"]>;

type Retry = { kind: "idle" | "sending" } | { kind: "error"; message: string; final: boolean };

export default function ProcessingScreen({ jobId }: { jobId: string }) {
  // Bumped after a retry is accepted, so the poll starts again.
  const [epoch, setEpoch] = useState(0);
  const feed = useJobStatus(jobId, 2000, epoch);
  const status = feed.kind === "ok" ? feed.status : null;
  const done = status?.state === "succeeded";
  const [retry, setRetry] = useState<Retry>({ kind: "idle" });

  // Milestones only ride on live documents, so keep the latest of each.
  const [milestones, setMilestones] = useState<Milestones>({});
  const incoming = status?.milestones;
  useEffect(() => {
    if (incoming) setMilestones((prev) => ({ ...prev, ...incoming }));
  }, [incoming]);

  /**
   * POST /jobs/{id}/retry. The API allows two retries, then answers 409
   * retries_exhausted with its own sentence, shown as-is. Any other 409 means
   * the job is no longer failed (a retry from another tab), so just watch it.
   */
  async function sendRetry() {
    setRetry({ kind: "sending" });
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
      const body = (await res.json().catch(() => null)) as { detail?: { error?: { code?: string; message?: string } } } | null;
      const error = typeof body?.detail === "object" ? body.detail.error : undefined;
      if (res.ok || (res.status === 409 && !error)) {
        setRetry({ kind: "idle" });
        setEpoch((e) => e + 1);
      } else if (error?.message) {
        setRetry({ kind: "error", message: error.message, final: error.code === "retries_exhausted" });
      } else {
        setRetry({ kind: "error", message: copy.retryFailed, final: false });
      }
    } catch {
      setRetry({ kind: "error", message: copy.retryFailed, final: false });
    }
  }

  if (status?.state === "failed" && status.error) {
    const final = !status.error.retryable || (retry.kind === "error" && retry.final);
    return (
      <StateScreen
        pose="sitback"
        title={copy.failedTitle}
        body={retry.kind === "error" ? retry.message : failedBody(status.error)}
        alert
        action={
          final
            ? { label: copy.addDifferent, href: "/upload" }
            : { label: retry.kind === "sending" ? copy.retrying : copy.retry, onClick: sendRetry, disabled: retry.kind === "sending" }
        }
      />
    );
  }

  const steps = flowSteps(status ? { ...status, milestones } : null);
  const current = steps.find((s) => s.state === "now");

  return (
    <main className="fd fd-proc">
      <Rail feed={feed} />
      <Room jobId={jobId} done={done} steps={steps} current={current} dancersIn={milestones.dancers != null} />
    </main>
  );
}

// ---------------------------------------------------------------------- rail

function Rail({ feed }: { feed: ReturnType<typeof useJobStatus> }) {
  const status = feed.kind === "ok" ? feed.status : null;
  const remaining = feed.kind === "ok" ? timeRemaining(feed.status, feed.elapsedMs) : null;
  const progress = status?.state === "succeeded" ? 1 : (status?.progress ?? 0);
  const message = status?.state === "succeeded" ? copy.steps.ready : status?.stage_message || copy.waiting;

  return (
    <div className="fd-rail">
      <div
        className="fd-rail-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label={message}
      >
        <i style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="fd-rail-row">
        <p aria-live="polite">
          <b>{message}</b>
          {remaining && status?.state !== "succeeded" ? <span className="fd-rail-meta"> {remaining}</span> : null}
        </p>
        <CopyLink />
      </div>
      {feed.kind === "unreachable" && <StateNote pose="look" message={copy.unreachable} />}
    </div>
  );
}

function CopyLink() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="fd-btn fd-btn-sm fd-btn-ghost"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          track("link_copied");
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

// ---------------------------------------------------------------------- room

function Room({
  jobId,
  done,
  steps,
  current,
  dancersIn,
}: {
  jobId: string;
  done: boolean;
  steps: Step[];
  current: Step | undefined;
  dancersIn: boolean;
}) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const [mirror, setMirror] = useState(false);
  const [muted, setMuted] = useState(true);
  const [paused, setPaused] = useState(false);
  /** The clip's width / height once its metadata is in: a wide clip gets a wide stage. */
  const [aspect, setAspect] = useState(0);

  useEffect(() => {
    setSrc(localClipUrl(jobId) ?? `/api/jobs/${encodeURIComponent(jobId)}/video`);
  }, [jobId]);

  useEffect(() => {
    if (video) video.playbackRate = speed;
  }, [video, speed, src]);

  const nextSpeed = useCallback(() => setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length]), []);
  const togglePlay = useCallback(() => {
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, [video]);

  // DESIGN.md §8 keys: M mirror, S speed, space play/pause.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === "m") setMirror((m) => !m);
      else if (k === "s") nextSpeed();
      else if (k === " ") {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nextSpeed, togglePlay]);

  return (
    <div
      className="fd-proc-grid"
      data-wide={aspect >= 1 ? "" : undefined}
      style={aspect ? ({ ["--ar" as string]: aspect } as React.CSSProperties) : undefined}
    >
      <div className="fd-pstage" onClick={togglePlay} role="button" tabIndex={-1} aria-label={copy.videoLabel}>
        <span className="fd-tag">{copy.videoLabel}</span>
        <div className="fd-mirror" style={{ transform: mirror ? "scaleX(-1)" : undefined }}>
          {src && (
            <video
              ref={setVideo}
              src={src}
              autoPlay
              muted={muted}
              playsInline
              loop
              onPlay={() => setPaused(false)}
              onPause={() => setPaused(true)}
              onLoadedMetadata={(e) => setAspect(e.currentTarget.videoWidth / (e.currentTarget.videoHeight || 1))}
            />
          )}
          <SkeletonOverlay jobId={jobId} video={video} available={dancersIn} />
        </div>
        {paused && <span className="fd-tag fd-tag-b">{copy.paused}</span>}
      </div>

      <div className="fd-panel">
        <h1 className="fd-h1 fd-h1-app">{done ? copy.readyTitle : copy.title}</h1>
        <p className="fd-sub">{done ? copy.readySubtitle : copy.subtitle}</p>

        <div className="fd-now">
          <Heartbeat done={done} />
          <div className="fd-now-meta">
            <b>{done ? copy.heartbeatDone : current?.note || copy.waiting}</b>
            {!done && <span>{copy.heartbeat}</span>}
          </div>
        </div>

        {done && (
          <Link href={handoffHref(jobId, speed, null)} className="fd-btn fd-btn-accent fd-go">
            {copy.open}
          </Link>
        )}

        <div className="fd-tools">
          <button type="button" className="fd-tool" aria-pressed={speed !== 1} onClick={nextSpeed}>
            {copy.speed(speed)}
          </button>
          <button type="button" className="fd-tool" aria-pressed={mirror} onClick={() => setMirror((m) => !m)}>
            {mirror ? copy.mirrorOn : copy.mirrorOff}
          </button>
          <button type="button" className="fd-tool" aria-pressed={!muted} onClick={() => setMuted((m) => !m)}>
            {muted ? copy.soundOff : copy.soundOn}
          </button>
        </div>

        <ol className="fd-steps">
          {steps.map((s) => (
            <li key={s.key} className={`fd-step-${s.state}`}>
              <b>{s.label}</b>
              <span>{s.note}</span>
            </li>
          ))}
        </ol>
        {!done && <p className="fd-note">{copy.closeable}</p>}
      </div>
    </div>
  );
}

/**
 * The count-off numeral as a heartbeat: 1 to 8 at a steady 60 a minute while
 * the job runs, deliberately unrelated to the music. Lands on 8 when the lesson
 * is ready. Reduced motion: a still dot, then 8.
 */
function Heartbeat({ done }: { done: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(prefersReducedMotion()), []);

  useEffect(() => {
    const n = el.current;
    if (!n || done || reduced) return;
    let i = 0;
    const tick = () => {
      i = (i % 8) + 1;
      n.textContent = String(i);
      n.classList.remove("fd-hit");
      void n.offsetWidth;
      n.classList.add("fd-hit");
    };
    tick();
    const id = setInterval(tick, HEARTBEAT_MS);
    return () => clearInterval(id);
  }, [done, reduced]);

  const still = done ? "8" : "·";
  // Keyed on its state: the tick writes textContent directly, which replaces
  // the text node React holds, so a new state remounts instead of patching it.
  return (
    <div key={`${done}-${reduced}`} ref={el} className={`fd-now-n${!done && reduced ? " fd-wait" : ""}`} aria-hidden="true">
      {still}
    </div>
  );
}
