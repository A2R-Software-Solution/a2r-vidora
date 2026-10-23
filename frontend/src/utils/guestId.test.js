import test from "node:test";
import assert from "node:assert/strict";
import { guestId } from "./guestId.js";

const memoryStorage = (initial = {}) => {
  const values = { ...initial };
  return { getItem: (key) => values[key] ?? null, setItem: (key, value) => { values[key] = value; } };
};

test("a browser keeps the same guest id", () => {
  const storage = memoryStorage();
  const first = guestId(storage);
  assert.match(first, /^[0-9a-f-]{36}$/);
  assert.equal(guestId(storage), first);
});

test("a tampered id is replaced", () => {
  const storage = memoryStorage({ vidora_guest_id: "not-a-uuid" });
  assert.notEqual(guestId(storage), "not-a-uuid");
});

test("blocked storage sends no id instead of failing", () => {
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => {} };
  assert.equal(guestId(blocked), null);
});
