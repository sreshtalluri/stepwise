import type { MotionResult } from "./motion";

/**
 * Fetching a lesson's MotionResult: retried when the failure is transient, and
 * started early by the processing screen so "Start learning" opens on a
 * document that is already here (or at least already on its way).
 *
 * Status codes are services/motion-api's: 409 not succeeded yet, 410 removed,
 * 404 unknown are answers and are never retried. 0 (network, a cut-off or
 * malformed body), 429 and 5xx are a bad moment, retried with backoff before
 * the learner ever sees the "reload" screen — the first open of a phone-tested
 * lesson (job_dc32…, 2026-09-25) failed once and loaded on a manual retry.
 */
export type DocLoad = { kind: "ok"; doc: MotionResult } | { kind: "error"; status: number };

export const RETRY_DELAYS_MS = [1000, 3000];

export function retryable(status: number): boolean {
  return status === 0 || status === 429 || status >= 500;
}

type Fetch = (url: string, init: RequestInit) => Promise<Response>;

async function once(url: string, fetchImpl: Fetch): Promise<DocLoad> {
  try {
    const res = await fetchImpl(url, { cache: "no-store" });
    if (!res.ok) return { kind: "error", status: res.status };
    const doc = (await res.json()) as MotionResult;
    // Shallow guard, same reasoning as isJobStatus in lib/jobStatus.ts.
    if (!Array.isArray(doc?.persons)) return { kind: "error", status: 0 };
    return { kind: "ok", doc };
  } catch {
    return { kind: "error", status: 0 };
  }
}

export async function fetchLessonDoc(
  url: string,
  fetchImpl: Fetch = (u, i) => fetch(u, i),
  delays: number[] = RETRY_DELAYS_MS,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<DocLoad> {
  for (let attempt = 0; ; attempt++) {
    const load = await once(url, fetchImpl);
    if (load.kind === "ok" || !retryable(load.status) || attempt >= delays.length) return load;
    await sleep(delays[attempt]);
  }
}

// ponytail: one entry, the lesson being handed off. Dropped once the lesson
// page has taken it (or it failed), so a later open refetches and a removal
// (410) is never hidden behind a cached copy.
let pending: { url: string; load: Promise<DocLoad> } | null = null;

/** Start (or join) loading `url`. The processing screen calls this the moment a job succeeds. */
export function loadLessonDoc(url: string, fetchImpl?: Fetch): Promise<DocLoad> {
  if (pending?.url === url) return pending.load;
  const load = fetchLessonDoc(url, fetchImpl);
  const entry = { url, load };
  pending = entry;
  void load.then((r) => {
    if (r.kind === "error" && pending === entry) pending = null;
  });
  return load;
}

/** The lesson page has the document: let go of it. */
export function forgetLessonDoc(url: string): void {
  if (pending?.url === url) pending = null;
}
