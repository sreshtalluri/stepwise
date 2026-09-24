"use client";

import { useEffect, useState } from "react";
import { processing } from "./copy";

// Type-only import: erased at build time, so nothing outside apps/web is
// bundled and no workspace/transpile config is needed. Queued / processing /
// failed state lives in the job-status contract and NEVER in MotionResult —
// see packages/motion-contract/schema/job-status.schema.json.
import type { JobStatus } from "../../../packages/motion-contract/src/ts/generated/job-status";

export type { JobStatus };

const STATES = ["queued", "processing", "succeeded", "failed"] as const;

/**
 * Minimum shape guard at the network boundary. The full ajv validator lives in
 * the contract package; pulling it into the browser bundle to re-check our own
 * API is not worth the kilobytes. This only has to stop a malformed payload
 * from rendering a broken screen.
 *
 * ponytail: shallow guard. Swap in @stepwise/motion-contract's validator if
 * the API ever gains a second producer.
 */
export function isJobStatus(value: unknown): value is JobStatus {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.job_id === "string" &&
    typeof v.stage_message === "string" &&
    STATES.includes(v.state as (typeof STATES)[number])
  );
}

/**
 * Loose time remaining — docs/DESIGN.md §7c. Never a false-precision
 * countdown, and never a hardcoded "about two minutes": the estimate is
 * extrapolated from how long *this* job has actually taken so far. The PRD's
 * 2–4 minute figure comes from an FPS number it says could not be re-verified,
 * so no surface states it as fact.
 *
 * Returns null when there is nothing honest to say yet.
 */
export function timeRemaining(
  status: Pick<JobStatus, "state" | "progress">,
  elapsedMs: number,
): string | null {
  if (status.state === "queued") return processing.queued;
  if (status.state !== "processing") return null;

  const p = status.progress;
  // Below 5% the extrapolation is noise, and elapsed must be long enough to
  // mean anything.
  if (p === null || p < 0.05 || elapsedMs < 4000) return null;
  if (p >= 0.95) return processing.almostDone;

  const remainingMs = (elapsedMs / p) * (1 - p);
  const minutes = Math.round(remainingMs / 60000);
  if (minutes < 1) return processing.almostDone;
  return processing.remaining(minutes);
}

/**
 * The clip the learner just picked, so the processing screen can play it
 * immediately instead of waiting for a round trip (DESIGN.md §7c: there is no
 * dead time). A blob URL survives a client-side route change but not a real
 * reload, which is correct — on a reopened link the screen falls back to the
 * service's copy.
 */
const CLIP_KEY = "stepwise.localclip.";

export function rememberLocalClip(jobId: string, blobUrl: string): void {
  try {
    sessionStorage.setItem(CLIP_KEY + jobId, blobUrl);
  } catch {
    /* fall back to the served copy */
  }
}

export function localClipUrl(jobId: string): string | null {
  try {
    return sessionStorage.getItem(CLIP_KEY + jobId);
  } catch {
    return null;
  }
}

export type JobFeed =
  | { kind: "loading" }
  | { kind: "ok"; status: JobStatus; history: string[]; elapsedMs: number }
  | { kind: "unreachable" };

/**
 * Polls the job service. The job survives a closed tab (it is a queue, not a
 * session), so this is a plain poll with no reconnect ceremony.
 *
 * `history` is the list of distinct stage messages this client has seen, in
 * order. The contract carries only the *current* stage, and inventing past
 * ones would be a lie — so the checklist on screen is exactly what the service
 * actually reported while we were watching.
 */
export function useJobStatus(jobId: string, intervalMs = 2000): JobFeed {
  const [feed, setFeed] = useState<JobFeed>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();
    let history: string[] = [];

    const poll = async () => {
      try {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
          cache: "no-store",
        });
        if (!res.ok) throw new Error(String(res.status));
        const body: unknown = await res.json();
        if (!isJobStatus(body)) throw new Error("malformed job status");
        if (cancelled) return;

        const message = body.stage_message.trim();
        if (message && history[history.length - 1] !== message) {
          history = [...history, message];
        }
        setFeed({
          kind: "ok",
          status: body,
          history,
          elapsedMs: Date.now() - startedAt,
        });
        if (body.state === "queued" || body.state === "processing") {
          timer = setTimeout(poll, intervalMs);
        }
      } catch {
        if (cancelled) return;
        setFeed((prev) => (prev.kind === "ok" ? prev : { kind: "unreachable" }));
        timer = setTimeout(poll, intervalMs * 2);
      }
    };

    let timer: ReturnType<typeof setTimeout> = setTimeout(poll, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, intervalMs]);

  return feed;
}
