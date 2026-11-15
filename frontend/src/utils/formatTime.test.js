import test from "node:test";
import assert from "node:assert/strict";
import { formatPreciseTime, formatTime } from "./formatTime.js";

test("precise times show a fraction only when there is one", () => {
  assert.deepEqual([0, 83, 83.45, 83.007, 59.9996, 3723.5].map(formatPreciseTime),
    ["00:00", "01:23", "01:23.45", "01:23.007", "01:00", "01:02:03.5"]);
  assert.equal(formatPreciseTime(null), "00:00");
  assert.equal(formatTime(83.9), "01:23");
});
