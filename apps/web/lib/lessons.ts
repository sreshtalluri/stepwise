import type { MotionResult } from "./motion";

/**
 * The dev fixtures the viewer can be pointed at. Built by `npm run assets`.
 *
 * Development only. Their "videos" are generated colour-bar test cards with
 * moving shapes, which on the public site read as a broken page, not an
 * example. In a production build this is empty: no Examples list, no
 * prerendered fixture routes, and /lesson/good-lesson is treated as an unknown
 * job id. NEXT_PUBLIC_SHOW_EXAMPLES=1 turns them back on for a preview build.
 */
const EXAMPLES_ENABLED =
  process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_SHOW_EXAMPLES === "1";

const FIXTURES: Record<string, { title: string }> = {
  "good-lesson": { title: "Everything worked — one dancer, a full turn" },
  "failure-lesson": { title: "Cropped feet, an occluded arm, and a re-entry" },
  "two-dancers": { title: "Two dancers, with a crossing" },
  "two-dancers-apart": { title: "Two dancers, far apart — switching cuts" },
  // Synthetic travel. This used to say "today's pipeline pins root_trajectory to the
  // origin"; it no longer does (world placement wired on `grounding-wiring`), but
  // these fixtures are still synthetic and still the only ones here with travel in
  // them — they are hand-built by `npm run assets`, not pipeline output, and nobody
  // has yet checked in a real placed clip to replace them. Titled accordingly.
  travelling: { title: "Synthetic travel — a dancer crossing the floor" },
  "travelling-no-floor": { title: "Synthetic travel, no floor — the usual case" },
  // The honesty case for world placement (OPEN-DECISIONS E6): a track too short for
  // the placement solve keeps a placeholder position that is not a place in the room.
  // One dancer travels, the other stays where their clip puts them.
  "unplaced-dancer": { title: "One dancer placed, one the pipeline could not place" },
  // Every other fixture is a 9:16 short; this is a 16:9 (1280x720) YouTube-shaped clip.
  "landscape-lesson": { title: "Landscape 16:9 — two dancers, a wide shot" },
};

export const LESSONS: Record<string, { title: string }> = EXAMPLES_ENABLED ? FIXTURES : {};

/**
 * The job id out of a pasted lesson or processing link ("…/lesson/job_abc",
 * "/job/job_abc?x"), or null. Fixture ids are not lessons anyone can remove.
 */
export function lessonIdFromLink(text: string): string | null {
  const m = text.trim().match(/\/(?:lesson|job)\/([^/?#\s]+)/);
  if (!m) return null;
  const id = decodeURIComponent(m[1]);
  return Object.hasOwn(LESSONS, id) ? null : id;
}

/** Where a link lesson's video came from: services/motion-api GET /jobs/{id}/source. */
export interface Credit {
  url: string;
  host: string;
  creator: string | null;
  /** From the post's caption and sound (ingest.credit), only when found there. */
  choreo: string | null;
  track: string | null;
  artist: string | null;
}

/** The API's answer as a Credit, or null. The URL goes in an href, so https only. */
export function parseCredit(x: unknown): Credit | null {
  const c = x as Partial<Credit> | null;
  if (typeof c?.url !== "string" || typeof c.host !== "string" || !c.url.startsWith("https://")) return null;
  const str = (v: unknown) => (typeof v === "string" && v ? v : null);
  return { url: c.url, host: c.host, creator: str(c.creator), choreo: str(c.choreo), track: str(c.track), artist: str(c.artist) };
}

export interface LessonSource {
  /** null for a job: the MotionResult carries no title. */
  title: string | null;
  docUrl: string;
  /** A job's creator credit (404 for an uploaded file); null for a fixture. */
  creditUrl: string | null;
  videoUrl: string;
  glbUrls: (doc: MotionResult) => string[];
}

/**
 * Where a lesson's document, video and GLBs live, from its id alone. A fixture id
 * reads the static files `npm run assets` wrote; anything else is a job_id and
 * goes through the `/api` rewrite in next.config.mjs to services/motion-api.
 *
 * Pure, so the page resolves it in the browser — the old server page read the
 * fixture with node:fs, which 500s in the Worker and 404'd every real job.
 */
export function lessonSource(id: string): LessonSource {
  // hasOwn, not LESSONS[id]: "constructor" is a job id, not Object's prototype.
  if (Object.hasOwn(LESSONS, id)) {
    return {
      title: LESSONS[id].title,
      docUrl: `/fixtures/${id}.json`,
      creditUrl: null,
      videoUrl: `/fixtures/${id}.mp4`,
      glbUrls: (doc) => doc.persons.map((p) => `/fixtures/${id}.${p.person_id}.glb`),
    };
  }
  const job = encodeURIComponent(id);
  return {
    title: null,
    docUrl: `/api/jobs/${job}/result`,
    creditUrl: `/api/jobs/${job}/source`,
    videoUrl: `/api/jobs/${job}/video`,
    glbUrls: (doc) =>
      doc.persons.map((p) => `/api/assets/${encodeURIComponent(p.animation.glb_asset_id)}`),
  };
}
