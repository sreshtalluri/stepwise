/**
 * Where a learner's authored counts and parts live.
 *
 * Two kinds of count grid exist and they are not the same thing:
 *
 *   1. `MotionResult.proposed_counts` — MACHINE, server-side, immutable, one
 *      per job. A guess from the clip's audio. Arrives with the document.
 *   2. `LessonStructure` — HUMAN, per learner, mutable. Re-anchored count 1,
 *      half/double tempo, named parts. This file.
 *
 * (2) cannot live in (1): `MotionResult` is the frozen output of a finished job
 * and every consumer holds the same copy of it. So the proposal is only ever a
 * STARTING POINT, and a human edit always wins — once a learner has touched the
 * grid, the proposal is never re-applied, not on reload and not on a second
 * visit.
 *
 * ── Storage: localStorage, and why that is the right amount today ────────────
 *
 * OPEN-DECISIONS D5 (accounts: none / magic link / OAuth) is OPEN. Authored
 * structure is per-learner by definition, and there is no learner to key it on
 * until D5 lands — a server-side store would have to invent an identity, which
 * is precisely the decision D5 exists to make. So it is per-browser, and the
 * UI does not claim otherwise.
 *
 * ── Where the server store attaches ─────────────────────────────────────────
 *
 * `load` and `save` below are the entire seam; nothing else in the app touches
 * storage. Once D5 lands:
 *
 *   - `save`  -> PUT  /lessons/{clip_id}/structure   (identity from the session)
 *   - `load`  -> GET  /lessons/{clip_id}/structure, falling back to the local
 *                copy so an offline or logged-out learner keeps working
 *   - the local copy stays as the write-through cache, so this file's callers
 *     do not change shape at all
 *
 * One thing to decide at that point and not before: what happens when the
 * stored structure and the local one disagree. Last-write-wins is wrong for a
 * learner who authored parts on their phone during class. Recorded here rather
 * than guessed at.
 *
 * ── Retention ───────────────────────────────────────────────────────────────
 *
 * D6/D7 delete server-side artifacts; a browser's localStorage is outside that
 * promise and is not covered by it. That is honest today only because nothing
 * here is derived from the video — it is counts and part names the learner
 * typed. If anything person-derived is ever added to this blob, it becomes an
 * artifact D7 has to be able to delete, and this comment is where that shows up.
 */

// Relative, same as lib/motion.ts reaches into motion-contract: there is no
// workspace root and no node_modules link between these packages.
import { normalizeStructure, startingStructure } from "../../../packages/navigation/src/core";
import type { LessonStructure } from "../../../packages/navigation/src/core";
import type { MotionResult } from "./motion";

/** Bumped only if the stored shape changes. An unreadable blob is discarded, never migrated blindly. */
const KEY_PREFIX = "stepwise.lesson-structure.v1.";

const key = (lessonId: string) => KEY_PREFIX + lessonId;

export interface StoredStructure {
  structure: LessonStructure;
  /**
   * True once a human has edited this. The whole point of storing it: it is
   * what makes "manual always wins" checkable rather than implied, and it is
   * what the surface reads to decide whether to still call the grid a guess.
   */
  authored: boolean;
}

export function load(lessonId: string, endS: number): StoredStructure | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key(lessonId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredStructure;
    if (!parsed?.structure?.grid || !Array.isArray(parsed.structure.parts)) return null;
    // Re-normalize on the way in rather than trusting the blob: the clip it was
    // authored against is the same clip, but a structure that has been edited
    // by hand in devtools, or written by an older build, must not be able to
    // put the count strip into a state the editor cannot get it out of.
    // Only a learner's own edits are restored. An untouched proposal is not
    // theirs to keep: saving it froze the counts at whatever the pipeline
    // proposed the first time the lesson was opened, so every later fix to the
    // beat grid (tempo, count 1) never reached anyone who had opened it before.
    if (parsed.authored !== true) return null;
    return { structure: normalizeStructure(parsed.structure, endS), authored: true };
  } catch {
    // Quota, private mode, a half-written blob. Losing part names is a bad day;
    // a lesson that will not open is a worse one.
    return null;
  }
}

export function save(lessonId: string, stored: StoredStructure): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key(lessonId), JSON.stringify(stored));
  } catch {
    /* see above */
  }
}

/**
 * The grid the surface opens on when nothing has been authored yet.
 *
 * The proposal wins over `startingStructure`'s flat 120-a-minute default when
 * there is one, because a measured guess beats an unmeasured one — but it is
 * still a guess, which is why the return value says where it came from instead
 * of quietly handing back a grid.
 */
export function openingStructure(doc: MotionResult, endS: number): { structure: LessonStructure; from: "hand" | "music" } {
  const proposed = doc.proposed_counts;
  if (!proposed) return { structure: startingStructure(endS), from: "hand" };
  // Parts are NOT proposed. The machine has no opinion about where a dance
  // divides — that is choreography, not audio — so the eights come from
  // `startingStructure`'s "one part per eight" rule laid over the proposed
  // grid, and the learner moves them.
  const base = startingStructure(endS, proposed.seconds_per_count);
  return {
    structure: normalizeStructure(
      {
        grid: {
          countOneS: proposed.count_one_s,
          secondsPerCount: proposed.seconds_per_count,
          countTotal: proposed.count_total,
        },
        parts: base.parts,
      },
      endS,
    ),
    from: "music",
  };
}
