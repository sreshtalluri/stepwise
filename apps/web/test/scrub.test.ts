import { test } from "node:test";
import assert from "node:assert/strict";

import { scrub, scrubText } from "../lib/scrub";

const ORIGIN = "https://stepwise.example";
const TIKTOK = "https://www.tiktok.com/@some.dancer/video/7301234567890123456?lang=en";
const PRESIGNED =
  "https://acct.r2.cloudflarestorage.com/stepwise/a.glb?X-Amz-Signature=deadbeef&X-Amz-Credential=AKIA123";

test("pasted links, signed URLs, handles and emails never survive", () => {
  const out = scrubText(
    `fetch ${PRESIGNED} failed for ${TIKTOK}; also youtu.be/dQw4w9WgXcQ, tiktok:7301234567890123456, a@b.com, @some.dancer`,
    ORIGIN,
  );
  for (const leak of ["tiktok.com", "some.dancer", "7301234567890123456", "deadbeef", "AKIA123", "dQw4w9WgXcQ", "a@b.com"]) {
    assert.ok(!out.includes(leak), `${leak} leaked: ${out}`);
  }
});

test("the page's own URL keeps its path and loses its query", () => {
  assert.equal(scrubText(`${ORIGIN}/lesson/c0ffee?src=${encodeURIComponent(TIKTOK)}#x`, ORIGIN), `${ORIGIN}/lesson/c0ffee`);
  // A lookalike host is not our origin.
  assert.equal(scrubText(`${ORIGIN}.evil.com/x`, ORIGIN), "[url]");
});

test("the whole event is walked; code locations are left alone", () => {
  const event = {
    exception: { values: [{ value: `load failed: ${TIKTOK}`, stacktrace: { frames: [{ filename: "app:///_next/x.js", context_line: "@media" }] } }] },
    breadcrumbs: [{ category: "fetch", data: { url: PRESIGNED, status_code: 403 } }],
    request: { url: `${ORIGIN}/job/abc?u=1` },
  };
  const out = scrub(event, ORIGIN);
  const body = JSON.stringify(out);
  assert.ok(!body.includes("tiktok") && !body.includes("X-Amz"), body);
  assert.equal(out.request.url, `${ORIGIN}/job/abc`);
  assert.equal(out.breadcrumbs[0].data.status_code, 403);
  assert.equal(out.exception.values[0].stacktrace.frames[0].context_line, "@media");
  assert.equal(out.exception.values[0].stacktrace.frames[0].filename, "app:///_next/x.js");
});
