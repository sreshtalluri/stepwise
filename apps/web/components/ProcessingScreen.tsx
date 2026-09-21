"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import DemoStage from "./DemoStage";
import { processing as copy } from "../lib/copy";
import { localClipUrl, timeRemaining, useJobStatus } from "../lib/jobStatus";

/**
 * Processing and the reveal — docs/DESIGN.md §7c and §7f.
 *
 * The design principle: there is no dead time, because the video is already
 * useful. The learner's own clip plays immediately with speed, mirror and loop
 * already working — those are 2D operations that need no GPU, so a learner can
 * start working on the dance the second they upload.
 *
 * Stage lines come from JobStatus.stage_message and are never invented here:
 * "Building the body — count 9 of 32", not "Detection complete" and never a
 * bare percentage. Queued / processing / failed state lives in the job-status
 * contract, never in MotionResult.
 */

const SPEEDS = [0.5, 0.75, 1];

export default function ProcessingScreen({ jobId }: { jobId: string }) {
  const feed = useJobStatus(jobId);
  const status = feed.kind === "ok" ? feed.status : null;
  const done = status?.state === "succeeded";

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

  return (
    <main className="wrap app-screen">
      <h1 className="app-title">{copy.title}</h1>
      <p className="muted">{copy.subtitle}</p>

      <div className="processing-grid">
        <ClipPlayer jobId={jobId} />

        <div>
          {/* The reveal fires the moment the job succeeds: one slow orbit,
              then it settles. Once per lesson, and never under reduced
              motion — the hook enforces both. */}
          <DemoStage
            clip={null}
            lessonId={jobId}
            revealArmed={done}
            height={300}
            showChips={done}
          />
          {done && (
            <Link href={`/lesson/${jobId}`} className="btn" style={{ marginTop: 16 }}>
              Open the lesson
            </Link>
          )}
        </div>
      </div>

      {!done && <Stages feed={feed} />}
    </main>
  );
}

function Stages({ feed }: { feed: ReturnType<typeof useJobStatus> }) {
  const status = feed.kind === "ok" ? feed.status : null;
  const history = feed.kind === "ok" ? feed.history : [];
  const remaining =
    feed.kind === "ok" ? timeRemaining(feed.status, feed.elapsedMs) : null;
  const progress = status?.progress ?? 0;

  return (
    <section className="stages">
      <div
        className="progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label={status?.stage_message || copy.queued}
      >
        <i style={{ width: `${Math.max(2, progress * 100)}%` }} />
      </div>

      <ol aria-live="polite">
        {history.map((line, i) => (
          <li key={line} className={i === history.length - 1 ? "stage-now" : "stage-done"}>
            {line}
          </li>
        ))}
      </ol>

      {remaining && <p className="muted">{remaining}</p>}
      {feed.kind === "unreachable" && (
        <p className="muted">
          We cannot reach the job right now. It keeps running — this page will
          catch up.
        </p>
      )}

      <p className="muted" style={{ marginTop: 14 }}>
        {copy.closeable}
      </p>
      <CopyLink />
    </section>
  );
}

function CopyLink() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-ghost"
      style={{ marginTop: 10 }}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          // Clipboard blocked: select the address bar instead. Saying nothing
          // is worse than saying what to do.
          setCopied(false);
        }
      }}
    >
      {copied ? copy.copied : copy.copyLink}
    </button>
  );
}

/**
 * The learner's clip, playable from the first second. Speed, mirror and loop
 * carry their state in the label (DESIGN.md §8) so one glance from across the
 * room tells you what is on.
 */
function ClipPlayer({ jobId }: { jobId: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const [mirror, setMirror] = useState(false);
  const [loop, setLoop] = useState(true);

  useEffect(() => {
    setSrc(localClipUrl(jobId) ?? `/api/jobs/${encodeURIComponent(jobId)}/video`);
  }, [jobId]);

  useEffect(() => {
    if (video.current) video.current.playbackRate = speed;
  }, [speed, src]);

  const nextSpeed = () => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]);

  return (
    <div>
      {/* Height, not aspect ratio: a 9:16 phone clip at half a desktop width
          is ~900px tall and pushes the stage list off the screen. The video is
          letterboxed inside a fixed stage instead, which also matches the 3D
          stage beside it. */}
      <div className="stage" style={{ height: "clamp(260px, 44vh, 420px)" }}>
        <span className="stage-label">{copy.videoLabel}</span>
        {src && (
          <video
            ref={video}
            src={src}
            autoPlay
            muted
            playsInline
            loop={loop}
            controls
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "contain",
              transform: mirror ? "scaleX(-1)" : undefined,
            }}
          />
        )}
      </div>

      <div className="tools">
        <button type="button" className="tool" onClick={nextSpeed}>
          {copy.speed(speed)}
        </button>
        <button
          type="button"
          className="tool"
          aria-pressed={mirror}
          onClick={() => setMirror((m) => !m)}
        >
          {mirror ? copy.mirrorOn : copy.mirrorOff}
        </button>
        <button
          type="button"
          className="tool"
          aria-pressed={loop}
          onClick={() => setLoop((l) => !l)}
        >
          {loop ? copy.loopOn : copy.loopOff}
        </button>
      </div>
      <p className="meta">{copy.toolsNote}</p>
    </div>
  );
}
