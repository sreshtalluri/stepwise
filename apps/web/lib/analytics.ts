/**
 * First-party product events (services/motion-api/analytics.py has the rules;
 * docs/research/identity-and-analytics.md §3 the design).
 *
 * What this does NOT do, on purpose: no cookie, no localStorage, no id of any
 * kind. The batch is `[{name, props, lesson?}]` and nothing else; the server
 * derives a one-day hash from the request and throws the key away at midnight.
 * No autocapture: only the names below, called by hand where the thing happens.
 * A browser sending Global Privacy Control or Do Not Track sends nothing.
 *
 * Batched in memory, sent every 15 s, at 20 events, and with sendBeacon when
 * the page is hidden or left, so closing the tab does not lose the last batch.
 */
export const EVENTS = [
  "lesson_opened",
  "play_seconds",
  "loop_created",
  "speed_changed",
  "build_up_toggled",
  "click_toggled",
  "view_toggled",
  "tap_on_one",
  "count_one_nudged",
  "count_one_alternate",
  "dancer_picked",
  "link_copied",
] as const;
export type EventName = (typeof EVENTS)[number];
export type Props = Record<string, string | number | boolean>;
export interface Event {
  name: EventName;
  props?: Props;
  lesson?: string;
}

export const PLAY_BUCKET_S = 30;
const MAX_BATCH = 20;

/** The queue and the play meter, with the transport injected (tests pass a fake). */
export function createAnalytics(send: (body: string) => void) {
  let queue: Event[] = [];
  let play = { s: 0, lesson: undefined as string | undefined };

  const flush = () => {
    while (queue.length) send(JSON.stringify(queue.splice(0, MAX_BATCH)));
  };
  const track = (name: EventName, props?: Props, lesson?: string) => {
    if (!(EVENTS as readonly string[]).includes(name)) return;
    queue.push({ name, ...(props ? { props } : {}), ...(lesson ? { lesson } : {}) });
    if (queue.length >= MAX_BATCH) flush();
  };
  /** The playing time that has not made a whole bucket yet, as one short bucket. */
  const flushPlay = () => {
    const s = Math.round(play.s);
    if (s >= 1) track("play_seconds", { seconds: Math.min(s, PLAY_BUCKET_S) }, play.lesson);
    play.s = 0;
  };
  /** Seconds of playing: every whole 30 s becomes one `play_seconds` event. */
  const addPlay = (seconds: number, lesson?: string) => {
    if (play.lesson !== lesson) flushPlay();
    play.lesson = lesson;
    play.s += Math.max(0, seconds);
    while (play.s >= PLAY_BUCKET_S) {
      track("play_seconds", { seconds: PLAY_BUCKET_S }, lesson);
      play.s -= PLAY_BUCKET_S;
    }
  };
  /** Page hidden or closing: the partial bucket, then everything, now. */
  const hide = () => {
    flushPlay();
    flush();
  };
  return { track, addPlay, flush, hide, pending: () => queue.length };
}

/** Referrer host only, and empty for our own pages or none. */
export function referrerHost(referrer: string, ownHost: string): string {
  try {
    const host = new URL(referrer).hostname.toLowerCase();
    return host === ownHost.toLowerCase() ? "" : host;
  } catch {
    return "";
  }
}

export function optedOut(nav: { globalPrivacyControl?: boolean; doNotTrack?: string | null }): boolean {
  return nav.globalPrivacyControl === true || nav.doNotTrack === "1";
}

// ---- the browser instance ----------------------------------------------------

const ENDPOINT = "/api/events";

function beacon(body: string) {
  try {
    if (navigator.sendBeacon?.(ENDPOINT, new Blob([body], { type: "application/json" }))) return;
    void fetch(ENDPOINT, { method: "POST", body, keepalive: true, headers: { "content-type": "application/json" } }).catch(() => {});
  } catch {
    /* analytics never breaks the page */
  }
}

let browser: ReturnType<typeof createAnalytics> | null | undefined;

function instance() {
  if (browser !== undefined) return browser;
  if (typeof window === "undefined" || optedOut(navigator as Navigator & { globalPrivacyControl?: boolean })) {
    return (browser = null);
  }
  browser = createAnalytics(beacon);
  const a = browser;
  window.setInterval(a.flush, 15_000);
  window.addEventListener("pagehide", a.hide);
  document.addEventListener("visibilitychange", () => document.visibilityState === "hidden" && a.hide());
  return a;
}

export function track(name: EventName, props?: Props, lesson?: string) {
  instance()?.track(name, props, lesson);
}

export function addPlay(seconds: number, lesson?: string) {
  instance()?.addPlay(seconds, lesson);
}
