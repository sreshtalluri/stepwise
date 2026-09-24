import { test } from "node:test";
import assert from "node:assert/strict";

import { listMyLessons, parse, recordOpened, upsert, without, withThumb } from "./myLessons";

const a = { id: "job_a", title: "Your lesson", durationS: 12, dancers: 1 };
const b = { id: "job_b", title: "Your lesson", durationS: 30, dancers: 2 };

test("upsert puts the newest first, dedupes, and keeps an earlier thumbnail", () => {
  let list = upsert([], a, 1);
  list = withThumb(list, "job_a", "data:image/jpeg;base64,xx");
  list = upsert(list, b, 2);
  list = upsert(list, a, 3);
  assert.deepEqual(list.map((l) => [l.id, l.lastOpened]), [["job_a", 3], ["job_b", 2]]);
  assert.equal(list[0].thumb, "data:image/jpeg;base64,xx");
  assert.ok(!("thumb" in list[1]));
});

test("the list is capped at 50", () => {
  let list: ReturnType<typeof parse> = [];
  for (let i = 0; i < 60; i++) list = upsert(list, { ...a, id: `job_${i}` }, i);
  assert.equal(list.length, 50);
  assert.equal(list[0].id, "job_59");
});

test("without removes only that lesson", () => {
  const list = upsert(upsert([], a, 1), b, 2);
  assert.deepEqual(without(list, "job_a").map((l) => l.id), ["job_b"]);
});

test("parse survives garbage", () => {
  assert.deepEqual(parse(null), []);
  assert.deepEqual(parse("{not json"), []);
  assert.deepEqual(parse('{"id":1}'), []);
  assert.deepEqual(parse('[{"id":"x"}, {"id":"y","title":"t","lastOpened":1}]').map((l) => l.id), ["y"]);
});

test("storage wrappers are no-ops without a window and never throw on a broken store", () => {
  assert.deepEqual(listMyLessons(), []);
  recordOpened(a); // no window: nothing happens
  const g = globalThis as { window?: unknown };
  g.window = {
    localStorage: {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceeded");
      },
    },
  };
  try {
    recordOpened(a);
    assert.deepEqual(listMyLessons(), []);
  } finally {
    delete g.window;
  }
});
