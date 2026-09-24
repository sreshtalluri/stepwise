import { test } from "node:test";
import assert from "node:assert/strict";

import * as copy from "../lib/copy";
// The navigation package's strings are user-facing in this app now that the
// lesson page renders <LessonNavigator>, so they belong in the same sweep.
// packages/navigation/src/copy.ts was shaped for exactly this and says so.
import { copy as navigation } from "../../../packages/navigation/src/copy";

/**
 * The copy lint. docs/DESIGN.md §7h records that the banned overclaim was
 * written twice during the design pass by the person who wrote the rule
 * against it — "that is gravity, not carelessness". This test is the guard
 * rail, so the third time is caught by CI rather than by a reader.
 *
 * Everything user-facing lives in lib/copy.ts, which is what makes one sweep
 * possible. If a string is added straight into a component, it escapes this
 * test — put it in lib/copy.ts instead.
 */

function collect(value: unknown, path: string, out: [string, string][]): void {
  if (typeof value === "string") out.push([path, value]);
  else if (typeof value === "function") {
    // copy entries that take a value (e.g. "About 3 minutes left.")
    try {
      collect((value as (n: number) => string)(3), path, out);
    } catch {
      /* not a simple formatter */
    }
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => collect(v, `${path}[${i}]`, out));
  } else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) collect(v, `${path}.${k}`, out);
  }
}

const lines: [string, string][] = [];
collect(copy, "copy", lines);
collect(navigation, "navigation", lines);

test("there is copy to check", () => {
  assert.ok(lines.length > 30, `only found ${lines.length} strings`);
});

test("no banned words — DESIGN.md §11", () => {
  const banned = [
    "elevate",
    "seamless",
    "unleash",
    "next-gen",
    "effortless",
    "powerful",
    "revolutionize",
    "revolutionise",
  ];
  for (const [path, line] of lines) {
    for (const word of banned) {
      assert.ok(
        !new RegExp(`\\b${word}`, "i").test(line),
        `${path} uses the banned word "${word}": ${line}`,
      );
    }
  }
});

test("no exclamation marks and no emoji as icons — DESIGN.md §11", () => {
  for (const [path, line] of lines) {
    assert.ok(!line.includes("!"), `${path} has an exclamation mark: ${line}`);
    assert.ok(
      !/\p{Extended_Pictographic}/u.test(line),
      `${path} contains an emoji: ${line}`,
    );
  }
});

test("sentence case — no ALL-CAPS labels, DESIGN.md §5", () => {
  for (const [path, line] of lines) {
    const shouty = line.match(/\b[A-Z]{3,}\b/g);
    assert.equal(
      shouty,
      null,
      `${path} has an ALL-CAPS run ${shouty?.join(", ")}: ${line}`,
    );
  }
});

test("no overclaim about unseen motion — DESIGN.md §7h", () => {
  // Case 2 (blocked) and case 3 (out of frame) were never seen and must never
  // be described as recovered. These patterns are the exact shapes the two
  // recorded violations took, plus the near neighbours.
  const overclaims = [
    /camera never (shot|saw|filmed)/i,
    /(angles?|moments?) (you|the camera) (never|didn't|did not) (shot|film|saw|capture)/i,
    /\b(recover|reconstruct|restore)s? (what|the moment|movement|motion) .*(hidden|blocked|unseen|missed)/i,
    /see (through|behind) (the )?(occlusion|whatever|anything)/i,
    /\bfills? in (the )?(missing|blocked|hidden)/i,
    /\bnever guess/i, // PRD §4: not literally achievable, so never promised
  ];
  for (const [path, line] of lines) {
    for (const pattern of overclaims) {
      assert.ok(
        !pattern.test(line),
        `${path} overclaims (${pattern}): ${line}`,
      );
    }
  }
});

test("the case-1 claim is not undersold — DESIGN.md §7h", () => {
  // The dancer turning away IS tracked, and orbiting to see them is the
  // product's best claim. Underclaiming it is a recorded failure mode too, so
  // the proof band must actually make the claim.
  assert.match(copy.marketing.proof.body, /turns? away/i);
  assert.match(copy.marketing.proof.body, /tracked/i);
});

test("marketing states no processing-time number — PRD §3, §7", () => {
  // The 2–4 minute figure derives from an FPS claim the PRD says could not be
  // re-verified. The processing screen may say a time because it extrapolates
  // from the live job; the marketing site may not, because it has no job.
  const marketingLines: [string, string][] = [];
  collect(copy.marketing, "marketing", marketingLines);
  // A duration: a number (or "a"/"two"/"a few") next to a time unit.
  const duration =
    /\b(\d+|a|an|one|two|three|a few|a couple of)[\s–-]*(to\s+\d+\s*)?(minute|hour)s?\b/i;
  for (const [path, line] of marketingLines) {
    assert.ok(!duration.test(line), `${path} states an unmeasured processing time: ${line}`);
  }
  // The clip-length cap is a real, enforced constraint and must be stated.
  assert.match(copy.marketing.steps.items[0].body, /60 seconds/);
});

test("upload constraints match the multi-dancer revision — PRD §5", () => {
  // "One dancer" was removed as a hard constraint on 2026-09-18. Stale copy in
  // DESIGN.md §7d/§11 still says it; this test stops it coming back.
  const all = copy.upload.worksBest.join(" ") + " " + copy.marketing.steps.items[0].body;
  assert.ok(
    !/\bone dancer\b(?!\s+or)/i.test(all),
    `upload copy caps the clip at one dancer: ${all}`,
  );
  assert.match(all, /several|or a few/i);
  // The constraints that ARE real (PRD §3 ingest row, §5) must still be stated.
  assert.match(all, /60 seconds/i);
  assert.match(all, /cuts/i);
  assert.match(all, /still/i);
});

test("the rights line exists and is plain — DESIGN.md §7d, OPEN-DECISIONS D8", () => {
  assert.equal(copy.upload.rights, "Only upload video you have the right to use.");
});

test("errors do not apologise or blame — DESIGN.md §11", () => {
  for (const [path, line] of Object.entries(copy.upload.errors)) {
    assert.ok(!/sorry|apolog|oops/i.test(line), `${path} apologises: ${line}`);
    assert.match(line, /try again|Trim|Pick/i, `${path} says what to do next`);
  }
});
