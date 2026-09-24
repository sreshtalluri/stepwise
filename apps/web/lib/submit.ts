import { upload as copy } from "./copy";
import { rememberLocalClip } from "./jobStatus";

/**
 * The two front doors, shared by the landing hero and /upload so they cannot
 * drift: a pasted link and a video file. Both answer a job id to route to, or
 * the sentence to show and what kind of failure it was (which picks the
 * figure and the one next step, components/StateScreen.tsx StateNote).
 *
 * Failure text comes from the service and is rendered as-is. The service is
 * the only thing that saw the failure, and inventing a friendlier local
 * sentence for it is exactly the §7h mistake (see lib/copy.ts's note).
 */
export type Failure = "limit" | "invite" | "refused" | "file" | "unreachable";
export type Submitted = { jobId: string } | { error: string; kind: Failure };

const MAX_SECONDS = 60;

/**
 * A failed response from the service. Its sentence when it wrote one, in the
 * `{detail: {error: {message}}}` shape; `fallback` (ours) when it did not.
 *
 * A 413 is special: the service's detail is a bare string ("Clip is too
 * large."), and the host in front of it can refuse a big body before the
 * service sees it, so it gets our own line rather than the connection one.
 */
export async function failureFrom(res: Response, fallback: string): Promise<{ error: string; kind: Failure }> {
  if (res.status === 413) return { error: copy.errors.tooLarge, kind: "file" };
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = body?.detail as { error?: { message?: unknown } } | undefined;
  const message = typeof detail === "object" && typeof detail?.error?.message === "string" ? detail.error.message : null;
  if (!message) return { error: fallback, kind: "unreachable" };
  const kind: Failure = res.status === 429 ? "limit" : res.status === 403 ? "invite" : "refused";
  return { error: message, kind };
}

export async function submitLink(url: string, invite: string): Promise<Submitted> {
  try {
    const res = await fetch("/api/clips/link", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Invite-Code": invite },
      body: JSON.stringify({ url: url.trim() }),
    });
    if (!res.ok) return failureFrom(res, copy.linkErrors.unreachable);
    const body = (await res.json().catch(() => null)) as { job_id?: string } | null;
    if (!body?.job_id) return { error: copy.linkErrors.unreachable, kind: "unreachable" };
    // No blob URL to hand the processing screen: the clip lives on the
    // service, and ProcessingScreen falls back to fetching it.
    return { jobId: body.job_id };
  } catch {
    return { error: copy.linkErrors.unreachable, kind: "unreachable" };
  }
}

export async function submitFile(file: File): Promise<Submitted> {
  if (!file.type.startsWith("video/")) return { error: copy.errors.wrongType, kind: "file" };
  const seconds = await readDuration(file);
  // A clip whose duration cannot be read is not rejected here: the service
  // normalises with ffprobe and is the authority. Only a confidently over-long
  // clip is stopped, to save the upload.
  if (seconds !== null && seconds > MAX_SECONDS + 0.5) return { error: copy.errors.tooLong, kind: "file" };

  try {
    const body = new FormData();
    // Field name and route both match services/motion-api's `POST /clips`.
    body.append("file", file);
    const res = await fetch("/api/clips", { method: "POST", body });
    // Same rule as the link door: when the service explains the failure
    // (a 429 says when to come back), show its words, not ours.
    if (!res.ok) return failureFrom(res, copy.errors.uploadFailed);
    const { job_id: jobId } = (await res.json()) as { job_id: string };
    // Not revoked: the processing screen plays this immediately, so there is
    // no dead time while the job runs (DESIGN.md §7c).
    rememberLocalClip(jobId, URL.createObjectURL(file));
    return { jobId };
  } catch {
    return { error: copy.errors.uploadFailed, kind: "unreachable" };
  }
}

/** Duration in seconds, or null if the browser cannot tell us. */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.onloadedmetadata = () => done(Number.isFinite(video.duration) ? video.duration : null);
    video.onerror = () => done(null);
    video.src = url;
  });
}
