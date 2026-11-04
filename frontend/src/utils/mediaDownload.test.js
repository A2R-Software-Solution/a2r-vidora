import test from "node:test";
import assert from "node:assert/strict";
import { downloadCost, downloadError, downloadFailureMessage, groupQualities, isDownloadActive } from "./mediaDownload.js";

test("cost is read from the priced options for the chosen quality", () => {
  const options = [{ code: "mp3_128", credit_cost: 3 }, { code: "mp4_720", credit_cost: 9 }];
  assert.equal(downloadCost(options, "mp4_720"), 9);
  assert.equal(downloadCost(options, "mp4_1080"), null);
  assert.equal(downloadCost(undefined, "mp3_128"), null);
});

test("qualities are split into audio and video groups", () => {
  const grouped = groupQualities([
    { code: "mp3_48", kind: "audio" }, { code: "mp4_360", kind: "video" }, { code: "mp3_256", kind: "audio" },
  ]);
  assert.deepEqual(grouped.audio.map((q) => q.code), ["mp3_48", "mp3_256"]);
  assert.deepEqual(grouped.video.map((q) => q.code), ["mp4_360"]);
});

test("only queued and processing jobs count as active", () => {
  assert.equal(isDownloadActive({ status: "queued" }), true);
  assert.equal(isDownloadActive({ status: "processing" }), true);
  assert.equal(isDownloadActive({ status: "completed" }), false);
  assert.equal(isDownloadActive(undefined), false);
});

test("failure messages say that credits came back for our faults", () => {
  assert.match(downloadFailureMessage({ status: "failed", error_code: "YOUTUBE_BLOCKED" }), /credits were returned/);
  assert.match(downloadFailureMessage({ status: "failed" }), /did not finish/);
});

test("API errors map to readable messages", () => {
  assert.match(downloadError({ response: { status: 402, data: {} } }), /download credits/);
  assert.match(downloadError({ response: { status: 429, data: {} } }), /Too many requests/);
  assert.equal(downloadError({ response: { status: 422, data: { detail: "We could not read this YouTube link." } } }),
    "We could not read this YouTube link.");
  assert.match(downloadError({}), /Network problem/);
});
