import test from "node:test";
import assert from "node:assert/strict";
import { shortCards, shortError, isShortExpired, isShortPending } from "./shorts.js";

test("changing suggestions keeps existing generated clips visible without duplicating matches", () => {
  const jobs = [{ id: "a", start_time: 0, end_time: 30, status: "completed" },
    { id: "b", start_time: 60, end_time: 90, status: "rendering" }];
  const cards = shortCards([{ title: "New title", start_time: 0, end_time: 30 }], jobs);
  assert.equal(cards.length, 2);
  assert.equal(cards[0].title, "New title");
  assert.equal(cards[0].job.id, "a");
  assert.equal(cards[1].job.id, "b");
});

test("jobs restore without regenerating suggestions", () => {
  assert.equal(shortCards([], [{ id: "a", start_time: 0, end_time: 30 }])[0].job.id, "a");
});

test("expiry hides completed media before scheduled cleanup", () => {
  const now = Date.parse("2026-10-05T10:00:00Z");
  assert.equal(isShortExpired({ status: "completed", expires_at: "2026-10-05T09:59:00Z" }, now), true);
  assert.equal(isShortExpired({ status: "completed", expires_at: "2026-10-05T10:01:00Z" }, now), false);
  assert.equal(isShortPending({ status: "rendering" }), true);
  assert.equal(isShortPending({ status: "failed" }), false);
});

test("validation error arrays are never rendered as React children", () => {
  const text = shortError({ response: { status: 422, data: { detail: [{ msg: "invalid range" }] } } });
  assert.equal(typeof text, "string");
  assert.match(shortError({ response: { status: 410 } }), /expired/);
  assert.match(shortError({ response: { status: 429 } }), /Wait/);
});
