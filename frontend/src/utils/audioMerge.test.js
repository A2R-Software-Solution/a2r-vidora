import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_LIMITS, buildMergeRequest, isMergeExpired, isMergePending, mergeCost, mergeError,
  mergeFailureMessage, parseTime, trackSeconds, validateMerge, validateTrack,
} from "./audioMerge.js";

const URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
const yt = (id, start, end) => ({ id, source: "youtube", url: URL, start, end });
const up = (id, start, end, file = { name: "a.mp3", size: 1000 }) => ({ id, source: "upload", file, start, end });

test("times parse as mm:ss, h:mm:ss or seconds and reject nonsense", () => {
  assert.equal(parseTime("1:00"), 60);
  assert.equal(parseTime("2:40"), 160);
  assert.equal(parseTime("0:00"), 0);
  assert.equal(parseTime("1:02:03"), 3723);
  assert.equal(parseTime("90"), 90);
  assert.equal(parseTime(" 1:30 "), 90);
  for (const bad of ["", "abc", "1:75", "-5", "1:2:3:4", "1.5", null, undefined]) assert.equal(parseTime(bad), null, String(bad));
});

test("track length needs a valid, increasing range", () => {
  assert.equal(trackSeconds(yt(1, "1:00", "2:40")), 100);
  assert.equal(trackSeconds(yt(1, "2:00", "1:00")), 0);
  assert.equal(trackSeconds(yt(1, "", "1:00")), 0);
});

test("cost matches the server: started minutes plus a fee per extra track", () => {
  assert.equal(mergeCost([yt(1, "1:00", "2:40"), up(2, "0:00", "1:15")]), 4);
  assert.equal(mergeCost([yt(1, "0:00", "4:00"), yt(2, "0:00", "4:00")]), 9);
  assert.equal(mergeCost(Array.from({ length: 5 }, (_, i) => yt(i, "0:00", "1:00"))), 9);
  assert.equal(mergeCost([yt(1, "0:00", "1:00"), yt(2, "", "")]), null);
  assert.equal(mergeCost([]), null);
  assert.equal(mergeCost([yt(1, "0:00", "0:30"), yt(2, "0:00", "0:30")], { ...DEFAULT_LIMITS, extra_track_credits: 0 }), 1);
});

test("each track is validated for its source and range", () => {
  assert.equal(validateTrack(yt(1, "1:00", "2:00")), "");
  assert.match(validateTrack({ ...yt(1, "1:00", "2:00"), url: "https://evil.com/x" }), /YouTube/);
  assert.match(validateTrack(yt(1, "2:00", "1:00")), /after/);
  assert.match(validateTrack(yt(1, "", "1:00")), /start/);
  assert.match(validateTrack(yt(1, "0:00", "11:00")), /at most 10 minutes/);
  assert.equal(validateTrack(up(1, "0:00", "1:00")), "");
  assert.match(validateTrack(up(1, "0:00", "1:00", null)), /Choose/);
  assert.match(validateTrack(up(1, "0:00", "1:00", { name: "a.exe", size: 5 })), /MP3/);
  assert.match(validateTrack(up(1, "0:00", "1:00", { name: "a.mp3", size: 0 })), /empty/);
  assert.match(validateTrack(up(1, "0:00", "1:00", { name: "a.mp3", size: 10 * 1024 * 1024 + 1 })), /larger than 10 MB/);
  assert.match(validateTrack({ ...up(1, "0:00", "3:00"), duration: 60 }), /only 01:00 long/);
});

test("the whole merge is checked for count, total length, upload size and crossfade", () => {
  const two = [yt(1, "0:00", "1:00"), yt(2, "0:00", "1:00")];
  assert.deepEqual(validateMerge(two, { crossfade: 0 }), { trackErrors: {}, formError: "" });
  assert.match(validateMerge([two[0]], { crossfade: 0 }).formError, /at least 2/);
  const many = Array.from({ length: 11 }, (_, i) => yt(i, "0:00", "0:30"));
  assert.match(validateMerge(many, { crossfade: 0 }).formError, /at most 10 tracks/);
  const long = Array.from({ length: 4 }, (_, i) => yt(i, "0:00", "10:00"));
  assert.match(validateMerge(long, { crossfade: 0 }).formError, /at most 30 minutes/);
  const big = [up(1, "0:00", "1:00", { name: "a.mp3", size: 9 * 1024 * 1024 }), up(2, "0:00", "1:00", { name: "b.mp3", size: 9 * 1024 * 1024 }),
    up(3, "0:00", "1:00", { name: "c.mp3", size: 9 * 1024 * 1024 })];
  assert.match(validateMerge(big, { crossfade: 0 }).formError, /total at most 25 MB/);
  assert.match(validateMerge([yt(1, "0:00", "0:05"), yt(2, "0:00", "1:00")], { crossfade: 3 }).formError, /twice/);
  assert.equal(validateMerge([yt(1, "0:00", "0:06"), yt(2, "0:00", "1:00")], { crossfade: 3 }).formError, "");
  assert.ok(validateMerge([yt(1, "2:00", "1:00"), yt(2, "0:00", "1:00")], { crossfade: 0 }).trackErrors[1]);
});

test("the request points each uploaded track at its own file", () => {
  const fileA = { name: "a.mp3", size: 1 };
  const fileB = { name: "b.mp3", size: 2 };
  const { spec, files } = buildMergeRequest(
    [up(1, "0:00", "1:00", fileA), yt(2, "1:00", "2:40"), up(3, "0:30", "1:30", fileB)],
    { outputFormat: "m4a", crossfade: 2 });
  assert.deepEqual(files, [fileA, fileB]);
  assert.deepEqual(spec.tracks.map((t) => t.file_index), [0, undefined, 1]);
  assert.deepEqual(spec.tracks[1], { source: "youtube", start_time: 60, end_time: 160, url: URL });
  assert.equal(spec.output_format, "m4a");
  assert.equal(spec.crossfade_seconds, 2);
});

test("job state helpers", () => {
  assert.equal(isMergePending({ status: "queued" }), true);
  assert.equal(isMergePending({ status: "processing" }), true);
  assert.equal(isMergePending({ status: "completed" }), false);
  const now = Date.parse("2026-10-25T10:00:00Z");
  assert.equal(isMergeExpired({ status: "completed", expires_at: "2026-10-25T09:00:00Z" }, now), true);
  assert.equal(isMergeExpired({ status: "completed", expires_at: "2026-10-25T11:00:00Z" }, now), false);
  assert.equal(isMergeExpired({ status: "expired", expires_at: "2026-10-26T11:00:00Z" }, now), true);
  assert.match(mergeFailureMessage("INVALID_RANGE"), /range/);
  assert.match(mergeFailureMessage("SOMETHING_NEW"), /credits were returned/);
});

test("errors become our own text, never raw objects", () => {
  assert.match(mergeError({ response: { status: 402 } }), /credits/);
  assert.match(mergeError({ response: { status: 413 } }), /too large/);
  assert.equal(typeof mergeError({ response: { status: 422, data: { detail: [{ msg: "x" }] } } }), "string");
  assert.equal(mergeError({ response: { status: 415, data: { detail: "Unsupported audio file." } } }), "Unsupported audio file.");
  assert.match(mergeError({ code: "ERR_NETWORK" }), /connect/);
});
