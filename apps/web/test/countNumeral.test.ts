import { test } from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CountNumeral } from "../components/lesson/CountNumeral";

const html = (c: number, ands: boolean, half = 1) => renderToStaticMarkup(createElement(CountNumeral, { c, total: 16, half, ands }));

test("the count strip shows the & after a count, or just the count when it is hidden", () => {
  assert.equal(html(3, true), '3<span class="ls-and" aria-hidden="true">&amp;</span>');
  assert.equal(html(3, true, 3.5), '3<span class="ls-and ls-on" aria-hidden="true">&amp;</span>', "lit on its off-beat");
  assert.equal(html(3, false), "3");
  assert.equal(html(11, false), "3", "an eight's counts read 1–8");
  assert.equal(html(17, true), "", "past the end of the dance: nothing");
});
