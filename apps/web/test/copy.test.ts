import { test } from "node:test";
import assert from "node:assert/strict";

import * as copy from "../lib/copy";

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
  // the landing's demo section must actually make the claim.
  assert.match(copy.marketing.demo.body, /turns? away/i);
  assert.match(copy.marketing.demo.body, /tracked/i);
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
  assert.match(copy.marketing.hero.facts.join(" "), /60 seconds/);
});

test("upload constraints match the multi-dancer revision — PRD §5", () => {
  // "One dancer" was removed as a hard constraint on 2026-09-18. Stale copy in
  // DESIGN.md §7d/§11 still says it; this test stops it coming back.
  const all = copy.upload.worksBest.join(" ") + " " + copy.marketing.hero.facts.join(" ");
  assert.ok(
    !/\bone dancer\b(?!\s+or)/i.test(all),
    `upload copy caps the clip at one dancer: ${all}`,
  );
  // "One to six" is the exact cap (process_clip.MAX_DANCERS = 6).
  assert.match(all, /several|or a few|one to six/i);
  // The constraints that ARE real (PRD §3 ingest row, §5) must still be stated.
  assert.match(all, /60 seconds/i);
  assert.match(all, /cuts/i);
  assert.match(all, /still/i);
});

test("the rights line exists and is plain — DESIGN.md §7d, OPEN-DECISIONS D8", () => {
  assert.equal(copy.upload.rights, "Only upload video you have the right to use.");
});

test("the link rights line is not the upload one — docs/research/link-ingestion.md", () => {
  // A pasted link is a weaker claim than a held file: almost nobody pasting a
  // TikTok has any right to it. Reusing the upload sentence would assert the
  // same thing about a case where it is not true, so the two must differ and
  // the link one must not tell anyone they "have the right" to a link.
  const link = copy.upload.link.rights;
  assert.notEqual(link, copy.upload.rights);
  assert.ok(
    !/right to (use|post|share)/i.test(link),
    `the link rights line borrows the upload claim: ${link}`,
  );
  // The takedown promise is back because its door exists: "Report or remove
  // this video" on every lesson, and the form on /privacy.
  assert.match(link, /remove/i);
  // And it must say plainly that we do the fetching, rather than leaving the
  // visitor to assume the link is just a reference.
  assert.match(link, /\bfetch\b/i);
});

test("no surface claims we checked or verified anything — DESIGN.md §7h, §12.13", () => {
  // §7h: "Copy may not say 'we check', 'we verify', or 'we have permission'.
  // We do none of those things." The link path is where this is most tempting,
  // because fetching feels like inspecting.
  const forbidden = [
    /\bwe (check|verify|confirm|review|vet)\b/i,
    /\bwe have permission\b/i,
    /\b(verified|approved|licen[cs]ed) (clip|video|link)s?\b/i,
    /\b(secure|protected|private by design)\b/i,
  ];
  for (const [path, line] of lines) {
    for (const pattern of forbidden) {
      assert.ok(!pattern.test(line), `${path} claims a check we do not do: ${line}`);
    }
  }
});

test("the link gate says what still works — DESIGN.md §11", () => {
  // An invite wall that only says "no" strands someone who came to learn a
  // dance. File upload is open to everyone and the line has to say so.
  const gated = copy.upload.link.gated;
  assert.match(gated, /invited/i);
  assert.match(gated, /file/i);
  // "Coming soon" names a date we have not got (§7h: no promise the code does
  // not keep).
  assert.ok(!/coming soon|shortly|any day/i.test(gated), gated);
});

test("errors do not apologise or blame — DESIGN.md §11", () => {
  const all = { ...copy.upload.errors, ...copy.upload.linkErrors };
  for (const [path, line] of Object.entries(all)) {
    assert.ok(!/sorry|apolog|oops/i.test(line), `${path} apologises: ${line}`);
    assert.match(line, /try again|Trim|Pick/i, `${path} says what to do next`);
  }
});

test("link failure text is not duplicated client-side — §7h honesty boundary", () => {
  // The service decides why a fetch failed and writes the sentence, because it
  // is the only thing that saw the failure (services/motion-api/ingest.py, and
  // its own lint in test_ingest.py). A second table of guesses here would
  // drift, and drift on this screen means telling someone their video is
  // private when we never learned that. So the client keeps exactly one
  // string: the one for "we never reached the service at all".
  assert.deepEqual(Object.keys(copy.upload.linkErrors), ["unreachable"]);
});

test("no em-dashes on the entry flow — flow redesign voice", () => {
  // The landing, upload and processing surfaces were rewritten without them,
  // and the stage messages the service sends now use commas too. The lesson's
  // strings are not swept here: they predate the rule.
  const entry: [string, string][] = [];
  collect({ marketing: copy.marketing, upload: copy.upload, processing: copy.processing }, "copy", entry);
  for (const [path, line] of entry) assert.ok(!line.includes("—"), `${path} has an em-dash: ${line}`);
});

test("privacy and removal copy match what the code does — §7h", () => {
  const all = copy.privacy.sections.flatMap((s) => s.items).join(" ");
  // retention.TTL_DAYS = 180. If that changes, this sentence changes with it.
  assert.ok(all.includes(
    "We keep the clip while the lesson exists. Lessons nobody opens for six months are deleted, and a removal request deletes one straight away.",
  ));
  // The takedown deletes for everyone (dedupe: one canonical lesson) and keeps nothing to restore.
  assert.equal(copy.removal.body,
    "This deletes the video and the 3D lesson for everyone who has the link. It can't be undone.");
  // No accounts: "my lessons" is this browser and must say so.
  assert.match(copy.myLessons.subtitle, /on this device/i);
  // The API's relationship enum, verbatim (services/motion-api/api.py RemovalRequest;
  // test_retention.py checks the same from the other side).
  assert.deepEqual(Object.keys(copy.removal.relationships),
    ["i_am_in_it", "under_18", "i_own_the_rights", "other", "illegal_sexual_content"]);
  // That last box preserves instead of deleting (retention.quarantine_clip), and both surfaces say so.
  assert.match(copy.removal.reportNote, /do not delete it yet/);
  assert.match(all, /instead of being deleted at once/);
  assert.match(all, /reported to the authorities as the law requires/);
  // Nothing there is to promise: no terms, no response time, no inbox.
  assert.ok(!/\b(terms|within \d+|hours?|we will respond|contact us)\b/i.test(all), all);
  // There is no app, only a website (1e680e3).
  for (const [path, line] of lines) assert.ok(!/\bthe app\b/i.test(line), `${path}: ${line}`);
});

test("the entry flow never makes 8 counts a rule — owner, 2026-09-23", () => {
  // "Step by step" is the name; a loop is as long as the learner sets it. The
  // processing page shows no counts at all (the early ones were off the beat).
  const entry: [string, string][] = [];
  collect({ marketing: copy.marketing, upload: copy.upload, processing: copy.processing }, "copy", entry);
  for (const [path, line] of entry) {
    assert.ok(!/8-counts?|eight-counts?|8 counts at a time|counts 1 to 8/i.test(line), `${path}: ${line}`);
  }
  assert.match(copy.marketing.hero.headlineAccent, /step by step/i);
  // The invite gate is stated wherever a link can be pasted, and the file door stays open.
  assert.match(copy.upload.link.gated, /invited/i);
  assert.match(copy.upload.link.gated, /file works for everyone/i);
});

test("the usage-counts section names exactly what lib/analytics.ts sends — §7h", async () => {
  const { EVENTS, PLAY_BUCKET_S } = await import("../lib/analytics");
  const usage = copy.privacy.sections.find((s) => s.heading === "Usage counts");
  assert.ok(usage, "/privacy must say what is collected");
  const text = usage.items.join(" ");
  // One phrase per client event: add an event, and this fails until /privacy says so.
  const said: Record<(typeof EVENTS)[number], RegExp> = {
    lesson_opened: /open a lesson/,
    play_seconds: new RegExp(`every ${PLAY_BUCKET_S} seconds of playing`),
    loop_created: /make a loop \(its length, where it starts and how you made it\)/,
    speed_changed: /change the speed/,
    build_up_toggled: /Build up/,
    click_toggled: /the click/,
    view_toggled: /a view/,
    tap_on_one: /correct count 1/,
    count_one_nudged: /correct count 1/,
    count_one_alternate: /correct count 1/,
    dancer_picked: /pick a dancer/,
    link_copied: /copy a link/,
  };
  for (const name of EVENTS) assert.match(text, said[name], name);
  // The server-side pair, the referrer rule, and the identifier promises.
  assert.match(text, /each clip added/);
  assert.match(text, /how each job ended/);
  assert.match(text, /its name only, not the page/);
  assert.match(text, /Nothing is stored in your browser for this/);
  assert.match(text, /used for one day and is then deleted/); // analytics_salts
  assert.match(text, /The address itself is not saved/);
  assert.match(text, /Global Privacy Control or Do Not Track/); // optedOut()
  assert.match(text, /kept for 13 months, then reduced to daily totals/); // analytics.rollup
  assert.doesNotMatch(text, /\b(anonymous|anonymi[sz]ed|never identif)/i, "a daily hash is pseudonymous, not anonymous");
});

test("the handover privacy line states only what the code does", () => {
  // retention.TTL_DAYS == 180 (six months since last open); removal is on every lesson.
  assert.match(copy.privacy.atHandover, /six months unopened/);
  assert.match(copy.privacy.atHandover, /remove it from the lesson page/);
  assert.doesNotMatch(copy.privacy.atHandover, /\b(never|forever|guarantee|secure|encrypted)\b/i);
});

test("state screens: one headline, one line, one action, each true today", () => {
  const load = copy.lesson.load;
  const screens: [string, string, string][] = [
    [load.notReady, load.notReadyBody, load.notReadyLink],
    [load.removed, load.removedBody, load.removedLink],
    [load.notFound, load.notFoundBody, load.notFoundLink],
    [load.failed, load.failedBody, load.failedLink],
    [copy.site.notFound.title, copy.site.notFound.body, copy.site.notFound.action],
    [copy.site.crashed.title, copy.site.crashed.body, copy.site.crashed.action],
    [copy.processing.failedTitle, copy.processing.failedRetryable, copy.processing.retry],
    [copy.myLessons.emptyTitle, copy.myLessons.emptyBody, copy.myLessons.emptyLink],
  ];
  for (const [title, body, action] of screens) {
    assert.match(title, /^[A-Z][^.]*\.$/, `headline is one sentence: ${title}`);
    assert.ok(body.length > 0 && body.length < 120, `one line: ${body}`);
    assert.match(action, /^[A-Z][^.]*$/, `action is a label, not a sentence: ${action}`);
  }
  // There is no app, only a website: not in any form.
  for (const [path, line] of lines) assert.ok(!/\bapps?\b/i.test(line), `${path}: ${line}`);
});

test("a removed lesson's page covers both ways a lesson goes — retention.TTL_DAYS = 180, removal", () => {
  // The sweeper writes the same tombstone as a takedown, so a 410 can be either.
  const body = copy.lesson.load.removedBody;
  assert.match(body, /when someone asks/);
  assert.match(body, /six months unopened/);
  assert.doesNotMatch(copy.lesson.load.removed, /asked|expired|you/i);
});

test("processing says only what the page observes, and never shows raw pipeline text", () => {
  // While it cannot reach the service the page cannot see the job, only its own polling.
  assert.match(copy.processing.unreachable, /This page keeps checking\./);
  assert.doesNotMatch(copy.processing.unreachable, /keeps running|will catch up/);
  // The retryable line is ours and hedged: the API says a retry "could plausibly" work.
  assert.match(copy.processing.failedRetryable, /may work/);
  assert.doesNotMatch(copy.processing.failedRetryable, /error:|exception|traceback/i);
});

test("the site's crash screen is not about lessons — global-error wraps every route", () => {
  for (const line of Object.values(copy.site.crashed)) assert.doesNotMatch(line, /lesson(?!s and clips)/i);
});

test("a too-large file is not told to check its connection", () => {
  assert.doesNotMatch(copy.upload.errors.tooLarge, /connection/i);
  // It names no byte count: the host in front of the service may stop a file below 200 MB.
  assert.doesNotMatch(copy.upload.errors.tooLarge, /\d/);
});
