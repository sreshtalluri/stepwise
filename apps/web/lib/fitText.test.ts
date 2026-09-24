import { test } from "node:test";
import assert from "node:assert/strict";

import { fitText } from "./fitText";
import { upload } from "./copy";

const opts = upload.link.placeholders;
const chars = (s: string) => s.length * 8;

test("the paste placeholder is the full line when it fits, shorter as the field narrows", () => {
  assert.equal(opts[0], "Paste a TikTok or YouTube link");
  assert.equal(fitText(opts, 1000, chars), opts[0]);
  assert.equal(fitText(opts, chars(opts[0]), chars), opts[0]);
  assert.equal(fitText(opts, chars(opts[0]) - 1, chars), opts[1]);
  assert.equal(fitText(opts, chars(opts[1]) - 1, chars), opts[2]);
  // Nothing fits: still the shortest, never empty.
  assert.equal(fitText(opts, 0, chars), opts[opts.length - 1]);
});

test("each placeholder is shorter than the one before it", () => {
  for (let i = 1; i < opts.length; i++) assert.ok(opts[i].length < opts[i - 1].length, opts[i]);
});
