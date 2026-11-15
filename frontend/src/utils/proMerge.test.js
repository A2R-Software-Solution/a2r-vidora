import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_LIMITS, mergeCost } from "./audioMerge.js";
import {
  buildProRequest, fitRange, locateInSequence, moveEdge, partSeconds, peakCount, peaksFromChannels, previewGain, proCost,
  recordingExtension, rulerStep, secondsBefore, shiftRange, songFromSource, sourceFailureMessage, totalSeconds,
  validateFile, validateLink, validatePro, zoomLevels,
} from "./proMerge.js";

const URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
const file = { name: "a.mp3", size: 1000 };
const song = (id, extra = {}) => ({ id, kind: "youtube", url: URL, sourceId: `src-${id}`, status: "ready", duration: 240, volume: 100, ...extra });
const upload = (id, extra = {}) => song(id, { kind: "upload", url: undefined, sourceId: undefined, file, ...extra });
const part = (id, songId, start, end, extra = {}) => ({ id, songId, start, end, fadeIn: 0, fadeOut: 0, ...extra });

test("peaks are the loudest sample of each slice across channels, scaled to 1", () => {
  assert.deepEqual(peaksFromChannels([[0, 0.1, -0.2, 0.05], [0, 0, 0, -0.4]], 2), [0.25, 1]);
  assert.deepEqual(peaksFromChannels([[0.5, -0.25]], 800), [1, 0.5]);
  assert.deepEqual(peaksFromChannels([[0, 0]], 2), [0, 0]);
  assert.deepEqual(peaksFromChannels([[]], 4), []);
});

test("a dragged range becomes whole seconds inside the song", () => {
  assert.deepEqual(fitRange(12.4, 40.6, 200, 600), { start: 12, end: 41 });
  assert.deepEqual(fitRange(40.6, 12.4, 200, 600), { start: 12, end: 41 });      // dragged right to left
  assert.deepEqual(fitRange(-5, 300, 200.7, 600), { start: 0, end: 200 });
  assert.deepEqual(fitRange(50, 50.2, 200, 600), { start: 50, end: 51 });          // never shorter than a second
  assert.deepEqual(fitRange(199.8, 200, 200, 600), { start: 199, end: 200 });
  assert.deepEqual(fitRange(10, 900, 1000, 600), { start: 10, end: 610 });         // capped, start kept
  assert.deepEqual(fitRange(10, 900, 1000, 600, "end"), { start: 300, end: 900 }); // capped, end kept
});

test("a moved range keeps its length and stops at the edges", () => {
  assert.deepEqual(shiftRange({ start: 10, end: 40 }, 5.4, 200), { start: 15, end: 45 });
  assert.deepEqual(shiftRange({ start: 10, end: 40 }, -50, 200), { start: 0, end: 30 });
  assert.deepEqual(shiftRange({ start: 10, end: 40 }, 500, 200), { start: 170, end: 200 });
});

test("a finer snap is optional: the same drag lands on tenths, hundredths or milliseconds", () => {
  assert.deepEqual(fitRange(12.3456, 40.6789, 200.75, 600), { start: 12, end: 41 });               // default: seconds
  assert.deepEqual(fitRange(12.3456, 40.6789, 200.75, 600, "start", 0.1), { start: 12.3, end: 40.7 });
  assert.deepEqual(fitRange(12.3456, 40.6789, 200.75, 600, "start", 0.01), { start: 12.35, end: 40.68 });
  assert.deepEqual(fitRange(12.3456, 40.6789, 200.75, 600, "start", 0.001), { start: 12.346, end: 40.679 });
  assert.deepEqual(fitRange(0, 999, 200.7567, 600, "start", 0.001), { start: 0, end: 200.756 });      // the whole song, never past its end
  assert.deepEqual(fitRange(0, 999, 200.7567, 600, "start", 1), { start: 0, end: 200 });
  assert.deepEqual(fitRange(5, 5.01, 200, 600, "start", 0.001), { start: 5, end: 5.1 });              // never shorter than 0.1s
  assert.deepEqual(shiftRange({ start: 10.25, end: 40.75 }, 5.37, 200, 0.1), { start: 15.6, end: 46.1 });
  assert.deepEqual(shiftRange({ start: 10.25, end: 40.75 }, 500, 200.5, 1), { start: 170, end: 200.5 });
});

test("moving one edge never changes the other, even when it was typed to the millisecond", () => {
  const typed = { start: 10.257, end: 40.75 };
  assert.deepEqual(moveEdge(typed, "end", 52.6, 200, 600), { start: 10.257, end: 53 });
  assert.deepEqual(moveEdge(typed, "end", 52.6, 200, 600, 0.1), { start: 10.257, end: 52.6 });
  assert.deepEqual(moveEdge(typed, "start", 3.4, 200, 600), { start: 3, end: 40.75 });
  assert.deepEqual(moveEdge(typed, "start", 83.4567, 200, 600, 0.001), { start: 40.65, end: 40.75 });   // stops 0.1s before the end
  assert.deepEqual(moveEdge(typed, "start", 99, 200, 600), { start: 40, end: 40.75 });                  // on a whole second when snapping to seconds
  assert.deepEqual(moveEdge(typed, "end", 0, 200, 600), { start: 10.257, end: 11 });
  assert.deepEqual(moveEdge(typed, "end", 0, 200, 600, 0.001), { start: 10.257, end: 10.357 });
  assert.deepEqual(moveEdge(typed, "end", 999, 200.4, 600), { start: 10.257, end: 200 });
  assert.deepEqual(moveEdge(typed, "end", 999, 200.4, 600, 0.001), { start: 10.257, end: 200.4 });
  assert.deepEqual(moveEdge({ start: 100, end: 700 }, "start", 0, 1000, 600), { start: 100, end: 700 });   // a part's length limit holds
  assert.deepEqual(moveEdge({ start: 100, end: 200 }, "end", 999, 1000, 600), { start: 100, end: 700 });
  assert.deepEqual(moveEdge({ start: 83.4, end: 120.5 }, "start", 83.456, 200, 600, 0.001), { start: 83.456, end: 120.5 });   // a typed time is taken as written
});

test("lengths and totals carry no float noise, and pricing rounds minutes the way the server does", () => {
  assert.equal(partSeconds(part(1, "a", 0.1, 0.3)), 0.2);
  assert.equal(totalSeconds([part(1, "a", 0, 20.1), part(2, "a", 0, 20.2), part(3, "a", 0, 19.7)]), 60);
  assert.equal(proCost([part(1, "a", 0, 20.1), part(2, "a", 0, 20.2), part(3, "a", 0, 19.7)]), 1 + 2);
  assert.equal(proCost([part(1, "a", 0, 60), part(2, "a", 0, 0.001)]), 2 + 1);
  assert.match(validatePro([song("a")], [part(1, "a", 5, 5.05), part(2, "a", 10, 20)], { crossfade: 0 }).partErrors[1], /at least 0.1/);
  assert.deepEqual(buildProRequest([song("a")], [part(1, "a", 83.456, 120.5), part(2, "a", 10, 20)], { outputFormat: "mp3", crossfade: 0 })
    .spec.tracks.map((track) => [track.start_time, track.end_time]), [[83.456, 120.5], [10, 20]]);
});

test("waveform detail and zoom levels follow the song's length", () => {
  assert.deepEqual([3, 16, 240, 900, 5000].map(peakCount), [800, 800, 12000, 45000, 45000]);
  assert.deepEqual(zoomLevels(240), [1, 2, 4, 8, 16, 32, 64]);
  assert.deepEqual(zoomLevels(10), [1, 2, 4, 8]);
  assert.deepEqual(zoomLevels(0.5), [1]);
});

test("pro costs exactly what the same sections cost in simple mode", () => {
  const parts = [part(1, "a", 60, 160), part(2, "a", 180, 200), part(3, "b", 0, 75)];
  const simple = [
    { source: "youtube", url: URL, start: "1:00", end: "2:40" },
    { source: "youtube", url: URL, start: "3:00", end: "3:20" },
    { source: "upload", file, start: "0:00", end: "1:15" },
  ];
  assert.equal(proCost(parts), mergeCost(simple));
  assert.equal(proCost(parts), 4 + 2);
  assert.equal(proCost([]), null);
  assert.equal(proCost([part(1, "a", 30, 30)]), null);
  assert.equal(proCost(parts, { ...DEFAULT_LIMITS, extra_track_credits: 0 }), 4);
});

test("parts are validated against their song and the merge limits", () => {
  const songs = [song("a"), upload("b", { duration: 90 })];
  const ok = [part(1, "a", 0, 60), part(2, "b", 10, 80)];
  assert.deepEqual(validatePro(songs, ok, { crossfade: 0 }), { partErrors: {}, formError: "" });
  assert.match(validatePro(songs, [part(1, "a", 0, 60)], { crossfade: 0 }).formError, /at least 2/);
  assert.match(validatePro(songs, [part(1, "a", 0, 60), part(2, "b", 10, 120)], { crossfade: 0 }).partErrors[2], /only 01:30/);
  assert.match(validatePro(songs, [part(1, "a", 0, 601), part(2, "b", 0, 30)], { crossfade: 0 }).partErrors[1], /10 minutes/);
  assert.match(validatePro(songs, [part(1, "a", 0, 8, { fadeIn: 5, fadeOut: 5 }), part(2, "b", 0, 30)], { crossfade: 0 }).partErrors[1], /fades/);
  assert.match(validatePro([song("a", { status: "loading" }), songs[1]], ok, { crossfade: 0 }).partErrors[1], /isn't loaded/);
  assert.match(validatePro(songs, [part(1, "a", 0, 60), part(2, "b", 0, 5)], { crossfade: 3 }).formError, /blend/);
  assert.match(validatePro(songs, Array.from({ length: 11 }, (_, i) => part(i, "a", 0, 10)), { crossfade: 0 }).formError, /at most 10 parts/);
  assert.match(validatePro([song("a", { duration: 900 })], Array.from({ length: 4 }, (_, i) => part(i, "a", 0, 500)), { crossfade: 0 }).formError, /30 minutes/);
  const big = upload("b", { file: { name: "b.mp3", size: DEFAULT_LIMITS.max_request_bytes + 1 } });
  assert.match(validatePro([song("a"), big], ok, { crossfade: 0 }).formError, /total at most/);
});

test("one uploaded file is counted and sent once however many parts use it", () => {
  const songs = [upload("u", { file: { name: "u.mp3", size: DEFAULT_LIMITS.max_request_bytes - 1 }, volume: 70 }), song("y")];
  const parts = [part(1, "u", 0, 30, { fadeIn: 2 }), part(2, "y", 60, 90), part(3, "u", 40, 70, { fadeOut: 3 })];
  assert.equal(validatePro(songs, parts, { crossfade: 0 }).formError, "");
  const { spec, files } = buildProRequest(songs, parts, { outputFormat: "m4a", crossfade: 2 });
  assert.deepEqual(files, [songs[0].file]);
  assert.deepEqual(spec, {
    tracks: [
      { source: "upload", file_index: 0, start_time: 0, end_time: 30, volume: 70, fade_in: 2, fade_out: 0 },
      { source: "youtube", url: URL, source_id: "src-y", start_time: 60, end_time: 90, volume: 100, fade_in: 0, fade_out: 0 },
      { source: "upload", file_index: 0, start_time: 40, end_time: 70, volume: 70, fade_in: 0, fade_out: 3 },
    ],
    output_format: "m4a",
    crossfade_seconds: 2,
  });
});

test("a time on the merged timeline maps to a part and an offset", () => {
  const parts = [part(1, "a", 10, 40), part(2, "b", 0, 20), part(3, "a", 100, 110)];
  assert.deepEqual(locateInSequence(parts, 0), { index: 0, offset: 0 });
  assert.deepEqual(locateInSequence(parts, 29.5), { index: 0, offset: 29.5 });
  assert.deepEqual(locateInSequence(parts, 30), { index: 1, offset: 0 });
  assert.deepEqual(locateInSequence(parts, 55), { index: 2, offset: 5 });
  assert.deepEqual(locateInSequence(parts, 999), { index: 2, offset: 10 });
  assert.equal(secondsBefore(parts, 2), 50);
});

test("preview loudness follows the volume and both fades", () => {
  const faded = part(1, "a", 10, 30, { fadeIn: 4, fadeOut: 5 });
  assert.equal(previewGain(faded, 80, 10), 0);
  assert.equal(previewGain(faded, 80, 12), 0.4);
  assert.equal(previewGain(faded, 80, 20), 0.8);
  assert.ok(Math.abs(previewGain(faded, 80, 29) - 0.16) < 1e-9);
  assert.equal(previewGain(part(1, "a", 10, 30), 100, 10), 1);
});

test("ruler labels thin out for long songs and narrow screens", () => {
  assert.equal(rulerStep(60, 700), 10);
  assert.equal(rulerStep(240, 700), 30);
  assert.equal(rulerStep(240, 320), 60);
  assert.equal(rulerStep(900, 320), 300);
  assert.equal(rulerStep(100000, 10), 600);
  // Zoomed in: the view shows only a few seconds, so labels go below a second.
  assert.equal(rulerStep(8, 700), 1);
  assert.equal(rulerStep(3.75, 700), 0.5);
  assert.equal(rulerStep(1, 700), 0.1);
});

test("a prepared YouTube source becomes a ready song, a failed one an error", () => {
  assert.deepEqual(songFromSource({ id: "s1", status: "processing" }), { sourceId: "s1" });
  assert.deepEqual(songFromSource({
    id: "s1", status: "ready", title: "My song", duration_seconds: 200, peaks: [0, 50, 100], preview_url: "https://x/p.mp3",
  }), { status: "ready", sourceId: "s1", name: "My song", duration: 200, peaks: [0, 0.5, 1], audioUrl: "https://x/p.mp3" });
  assert.equal(songFromSource({ id: "s1", status: "ready", title: null, duration_seconds: 5, peaks: null, preview_url: "u" }).name, "YouTube song");
  assert.match(songFromSource({ id: "s1", status: "failed", error_code: "TOO_LONG" }).error, /too long/);
  assert.equal(songFromSource({ id: "s1", status: "expired", error_code: null }).status, "error");
});

test("links, files, failures and recordings are described for the user", () => {
  assert.equal(validateLink(` ${URL} `), "");
  assert.match(validateLink("https://evil.com/x"), /YouTube/);
  assert.equal(validateFile(file), "");
  assert.match(validateFile(null), /Choose/);
  assert.match(validateFile({ name: "a.exe", size: 10 }), /MP3/);
  assert.match(validateFile({ name: "a.mp3", size: 0 }), /empty/);
  assert.match(validateFile({ name: "a.mp3", size: DEFAULT_LIMITS.max_upload_bytes + 1 }), /larger/);
  assert.match(sourceFailureMessage("TOO_LONG"), /too long/);
  assert.match(sourceFailureMessage("SOMETHING_NEW"), /couldn't load/);
  assert.deepEqual(["audio/webm;codecs=opus", "audio/mp4", "audio/ogg", ""].map(recordingExtension), [".webm", ".m4a", ".ogg", ".webm"]);
});
