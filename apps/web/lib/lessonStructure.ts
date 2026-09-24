/**
 * Where the learner's counts and parts live.
 *
 * Two kinds of structure meet here and must not be confused (this is the
 * distinction the whole feature turns on):
 *
 *   MACHINE  `MotionResult.beat_proposal` -- one guess per clip, produced
 *            server-side, immutable, carries its own confidence and its
 *            half/double alternates. Never edited.
 *   HUMAN    `LessonStructure` -- the counts and parts the learner authored
 *            (PRD §5: "manually set counts and named parts"). Mutable,
 *            per-learner, and it always wins.
 *
 * The human side is stored in localStorage, not on the server, because there
 * is nowhere on the server to put it: OPEN-DECISIONS.md D5 (accounts) is
 * unresolved, so there is no identity to key per-learner state by. That is a
 * real MVP limitation and is stated plainly rather than papered over: authored
 * counts live in one browser, survive reload, and do not follow a share link.
 *
 * WHERE THE SERVER STORE ATTACHES. `restore()` and `save()` below are the
 * entire seam. When D5 lands they become the offline half of a read-through
 * cache -- both are already called after mount, which is where a fetch has to
 * happen anyway:
 *
 *     restore(id)  ->  GET  /lessons/{id}/structure   (falling back to local)
 *     save(id)     ->  PUT  /lessons/{id}/structure   (writing local first)
 *
 * keyed by whatever D5 settles on (the current recommendation on branch
 * `research-identity-analytics` is an anonymous creator token in the browser,
 * optionally bound later by magic link -- which is exactly the shape this
 * key already has). Nothing else in the app reads localStorage, and
 * `MotionResult` does not change at all, so that swap is additive: no contract
 * change, no schema version, no migration of the documents the pipeline wrote.
 */
import type { LessonStructure } from "../../../packages/navigation/src/core";
import { normalizeStructure, proposedGrid, startingStructure } from "../../../packages/navigation/src/core";
import type { MotionResult } from "./motion";

/**
 * Versioned so a later shape change can be detected and dropped rather than
 * crashing on a stale object. `lesson` scopes it: two lessons in one browser
 * keep separate counts, which is the whole point of naming parts.
 */
const KEY_PREFIX = "stepwise.lesson-structure.v1.";

const keyFor = (lessonId: string) => KEY_PREFIX + lessonId;

/**
 * The structure to open a lesson with before any browser state is consulted:
 * the machine's proposal if there is one, otherwise navigation's own plain
 * default grid.
 *
 * PURE ON PURPOSE. The lesson page is prerendered, so this has to produce the
 * same answer on the server and on the client or hydration mismatches. That is
 * why reading the saved copy is a separate, after-mount step (`restore`) and
 * not folded in here.
 *
 * `endS` is the clip's end per the contract -- `sample_times_s[N-1]`, not
 * `source_video.duration_s`.
 */
export function seed(doc: MotionResult, endS: number): LessonStructure {
  const proposed = proposedGrid(doc);
  if (!proposed) return startingStructure(endS);
  // One part per eight, as `startingStructure` does -- eights are how dances
  // are taught, and the proposal says nothing about phrasing.
  return normalizeStructure({ ...startingStructure(endS, proposed.secondsPerCount), grid: proposed }, endS);
}

/**
 * What this browser last saved for this lesson, or null. Client-only: call it
 * from an effect, never during render.
 */
export function restore(lessonId: string, endS: number): LessonStructure | null {
  const saved = readSaved(lessonId);
  return saved ? normalizeStructure(saved, endS) : null;
}

export function save(lessonId: string, structure: LessonStructure): void {
  try {
    window.localStorage.setItem(keyFor(lessonId), JSON.stringify(structure));
  } catch {
    // Private mode, or quota. Losing authored counts on reload is bad but not
    // worth taking the lesson down for -- the session in front of the learner
    // keeps working.
  }
}

function readSaved(lessonId: string): LessonStructure | null {
  try {
    const raw = window.localStorage.getItem(keyFor(lessonId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LessonStructure;
    // Shape check, not a schema: a half-written or hand-edited entry should
    // fall back to the proposal rather than throw inside a render.
    if (!parsed?.grid || !Array.isArray(parsed.parts)) return null;
    if (!(parsed.grid.secondsPerCount > 0)) return null;
    return parsed;
  } catch {
    return null;
  }
}
