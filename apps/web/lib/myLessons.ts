/**
 * "My lessons": the lessons this browser has opened, kept in localStorage.
 *
 * There are no accounts (OPEN-DECISIONS D5), so this is the only memory of
 * "mine" there is, and the page says "Saved on this device" because that is
 * exactly what it is. Nothing here is sent anywhere.
 *
 * The thumbnail is the one person-derived thing in it: a ~120px JPEG of the
 * lesson's own first frame. A server-side removal (D7) cannot reach into a
 * browser, so the loader forgets an entry the moment its link answers 410,
 * and "Remove from my lessons" drops it here. /privacy says both.
 *
 * The list logic is pure (arrays in, arrays out) so it is testable without a
 * DOM; the storage wrappers below are the only impure part, and every one of
 * them swallows storage failures (private mode, quota) — a lesson that will
 * not open because a bookmark list failed to save is the worse outcome.
 */

export interface SavedLesson {
  id: string;
  title: string;
  durationS: number;
  dancers: number;
  /** ms since epoch */
  lastOpened: number;
  /** data:image/jpeg URL, absent when the frame could not be read (e.g. CORS-tainted). */
  thumb?: string;
}

const KEY = "stepwise.my-lessons.v1";
// ponytail: newest 50 only — at ~6 KB a thumbnail that is ~300 KB of a ~5 MB quota.
const MAX = 50;

export function parse(raw: string | null): SavedLesson[] {
  if (!raw) return [];
  try {
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list.filter(
      (l): l is SavedLesson =>
        typeof l?.id === "string" && typeof l.title === "string" && typeof l.lastOpened === "number",
    );
  } catch {
    return [];
  }
}

/** Newest first; re-opening moves a lesson to the top and keeps its thumbnail. */
export function upsert(
  list: SavedLesson[],
  entry: Omit<SavedLesson, "lastOpened">,
  now: number,
): SavedLesson[] {
  const old = list.find((l) => l.id === entry.id);
  const next: SavedLesson = { ...entry, thumb: entry.thumb ?? old?.thumb, lastOpened: now };
  if (!next.thumb) delete next.thumb;
  return [next, ...list.filter((l) => l.id !== entry.id)].slice(0, MAX);
}

export function without(list: SavedLesson[], id: string): SavedLesson[] {
  return list.filter((l) => l.id !== id);
}

export function withThumb(list: SavedLesson[], id: string, thumb: string): SavedLesson[] {
  return list.map((l) => (l.id === id ? { ...l, thumb } : l));
}

// --- storage ----------------------------------------------------------------

function read(): SavedLesson[] {
  try {
    return parse(window.localStorage.getItem(KEY));
  } catch {
    return [];
  }
}

function write(list: SavedLesson[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* see header */
  }
}

export function listMyLessons(): SavedLesson[] {
  return typeof window === "undefined" ? [] : read();
}

export function recordOpened(entry: Omit<SavedLesson, "lastOpened">): void {
  if (typeof window === "undefined") return;
  write(upsert(read(), entry, Date.now()));
}

export function forgetLesson(id: string): void {
  if (typeof window === "undefined") return;
  write(without(read(), id));
}

export function hasThumb(id: string): boolean {
  return typeof window !== "undefined" && !!read().find((l) => l.id === id)?.thumb;
}

/**
 * Grab the first frame of the lesson's own video into a tiny JPEG and attach
 * it. Best effort and silent: a video served cross-origin without CORS
 * headers either fails to load with `crossOrigin` set or taints the canvas,
 * and in both cases the lesson simply has no picture.
 */
export function captureThumb(id: string, videoUrl: string): void {
  if (typeof document === "undefined") return;
  const video = document.createElement("video");
  video.crossOrigin = "anonymous";
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  const done = () => {
    video.removeAttribute("src");
    video.load();
  };
  video.addEventListener("error", done, { once: true });
  video.addEventListener(
    "loadeddata",
    () => {
      try {
        // Scaled by the SHORT side: the list crops it into a 56x72 portrait card
        // (object-fit: cover), and a 16:9 frame sized by its width left the visible
        // middle about 50 px wide — blurry at 2x.
        const k = 144 / (Math.min(video.videoWidth, video.videoHeight) || 144);
        const w = Math.round(video.videoWidth * k) || 144;
        const h = Math.round(video.videoHeight * k) || 144;
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d")?.drawImage(video, 0, 0, w, h);
        const thumb = canvas.toDataURL("image/jpeg", 0.6); // throws when tainted
        write(withThumb(read(), id, thumb));
      } catch {
        /* tainted or no 2d context: no picture */
      }
      done();
    },
    { once: true },
  );
  video.src = videoUrl;
}
