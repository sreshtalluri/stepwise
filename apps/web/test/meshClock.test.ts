import { test } from "node:test";
import assert from "node:assert/strict";
import { meshTimeAt } from "../components/lesson/hooks";

test("meshTimeAt: carries the last video frame forward to when the canvas is shown", () => {
  const frame = { media: 10, at: 1000 };
  assert.equal(meshTimeAt(frame, 1000, 1), 10); // shown on the same vsync as the video
  assert.ok(Math.abs(meshTimeAt(frame, 1016, 1) - 10.016) < 1e-9); // a frame later
  assert.ok(Math.abs(meshTimeAt(frame, 1016, 0.5) - 10.008) < 1e-9); // slowed lesson
  assert.equal(meshTimeAt(frame, 990, 1), 10); // never behind the frame
  assert.equal(meshTimeAt(frame, 5000, 1), 10.1); // a stalled video: clamped
});
