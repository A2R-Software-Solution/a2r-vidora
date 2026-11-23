import assert from "node:assert/strict";
import test from "node:test";
import {
  activeCaptionIndex, autoSync, captionErrors, captionsForRequest, cleanText, hexToRgba, karaokeWords, previewScale,
} from "./reelEditor.js";

const line = (start, end, text = "hello") => ({ start, end, text });

test("captions are checked like the server does", () => {
  assert.deepEqual(captionErrors([line(0, 2), line(2, 4)], 30), []);
  assert.match(captionErrors([], 30)[0], /at least one/);
  assert.match(captionErrors([line(0, 2), line(1, 3)], 30).join(), /overlaps/);
  assert.match(captionErrors([line(0, 31)], 30).join(), /after the clip/);
  assert.match(captionErrors([line(3, 3)], 30).join(), /end after it starts/);
  assert.match(captionErrors([line(0, 2, "  ")], 30).join(), /empty/);
  assert.match(captionErrors([line(0, 2, "x".repeat(121))], 30).join(), /120/);
  assert.match(captionErrors(Array.from({ length: 61 }, (_, i) => line(i * 0.5, i * 0.5 + 0.4)), 60).join(), /at most 60/);
});

test("subtitle markup characters are stripped", () => {
  assert.equal(cleanText(" a {b}\\c <d>\n e "), "a b c d e");
});

test("auto sync spreads lines over the clip without gaps or overlap", () => {
  const synced = autoSync([line(5, 6, "short"), line(9, 9.5, "a much longer line of text"), line(1, 2, "  ")], 30);
  assert.equal(synced.length, 2);
  assert.equal(synced[0].start, 0);
  assert.equal(synced[0].end, synced[1].start);
  assert.equal(synced[1].end, 30);
  assert.ok(synced[1].end - synced[1].start > synced[0].end - synced[0].start);
  assert.deepEqual(captionErrors(synced, 30), []);
  assert.deepEqual(autoSync([], 30), []);
});

test("the active caption follows the playback time", () => {
  const captions = [line(0, 2), line(3, 5)];
  assert.equal(activeCaptionIndex(captions, 1), 0);
  assert.equal(activeCaptionIndex(captions, 2.5), -1);
  assert.equal(activeCaptionIndex(captions, 3), 1);
  assert.equal(activeCaptionIndex(captions, 5), -1);
});

test("karaoke lights words in order", () => {
  const lit = (time) => karaokeWords("one two three", 0, 3, time).map((item) => item.lit);
  assert.deepEqual(lit(0), [true, false, false]);
  assert.deepEqual(lit(3), [true, true, true]);
  assert.deepEqual(lit(-1), [false, false, false]);
});

test("scale and colours", () => {
  assert.equal(previewScale(540, 960), 0.5);
  assert.equal(previewScale(960, 540), 0.5);
  assert.equal(hexToRgba("#FF8000", 50), "rgba(255, 128, 0, 0.5)");
  assert.equal(hexToRgba("nope", 200), "rgba(0, 0, 0, 1)");
});

test("requests carry rounded, cleaned captions", () => {
  assert.deepEqual(captionsForRequest([line(0.123456, 1.987654, " hi <b> ")]), [{ start: 0.12, end: 1.99, text: "hi b" }]);
});
