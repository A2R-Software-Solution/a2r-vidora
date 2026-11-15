// Song Merger Pro editor rules, shared by the editor and its tests. A "song" is
// a loaded source (YouTube link, uploaded file or microphone recording); a
// "part" is one section of a song. Parts play in list order and are sent to the
// same merge API as Simple mode (one track per part), so the price is the same.
import { formatTime } from "./formatTime.js";
import { YOUTUBE_LINK_MESSAGE, isYouTubeVideoUrl } from "./videoInput.js";
import {
  DEFAULT_LIMITS, MIN_TRACKS, MIN_TRACK_SECONDS, UPLOAD_EXTENSIONS, fileExtension, megabytes, toMillis,
} from "./audioMerge.js";

export const FADE_CHOICES = [0, 1, 2, 3, 5, 10];
export const MIN_PART_SECONDS = MIN_TRACK_SECONDS;
// What a dragged edge lands on. Seconds unless the user picks something finer;
// typed times are always exact to the millisecond.
export const SNAP_CHOICES = [[1, "Seconds"], [0.1, "Tenths (0.1 s)"], [0.01, "Hundredths (0.01 s)"], [0.001, "Milliseconds"]];
export const ZOOM_LEVELS = [1, 2, 4, 8, 16, 32, 64];

// Waveform detail: 50 slices a second (enough to zoom in), within bounds. Same rule as the server.
export const peakCount = (seconds) => Math.min(Math.max(Math.round(seconds * 50), 800), 45000);

// Zoom levels that still show at least a second of the song.
export const zoomLevels = (duration) => ZOOM_LEVELS.filter((level) => level === 1 || duration / level >= 1);

export const SOURCE_FAILURES = {
  TOO_LONG: "This video is too long for the editor. Use a shorter video, or Simple mode for long ones.",
  UNSUPPORTED_MEDIA: "Live streams and videos without a known length can't be loaded.",
  YOUTUBE_BLOCKED: "YouTube is temporarily blocking us. Please try again in a few minutes.",
  QUEUE_UNAVAILABLE: "We couldn't start loading this song. Please try again.",
  TIMED_OUT: "Loading this song took too long. Please try again.",
};

export function sourceFailureMessage(code) {
  return SOURCE_FAILURES[code] ?? "We couldn't load this song. Check the link and try again.";
}

// What a server-prepared YouTube source means for its song in the editor.
export function songFromSource(source) {
  if (source.status === "ready") {
    return {
      status: "ready", sourceId: source.id, name: source.title || "YouTube song",
      duration: source.duration_seconds, peaks: (source.peaks || []).map((peak) => peak / 100),
      audioUrl: source.preview_url,
    };
  }
  if (source.status === "failed" || source.status === "expired") {
    return { status: "error", error: sourceFailureMessage(source.error_code) };
  }
  return { sourceId: source.id };   // still being prepared
}

// Loudest value of each of `count` equal slices, scaled so the loudest slice is 1.
// `channels` are arrays of samples in -1..1 (the Web Audio channel data).
export function peaksFromChannels(channels, count = 800) {
  const length = channels[0]?.length ?? 0;
  if (!length) return [];
  const slices = Math.min(count, length);
  const peaks = new Array(slices).fill(0);
  for (const samples of channels) {
    for (let i = 0; i < slices; i += 1) {
      const end = Math.floor(((i + 1) * length) / slices);
      let peak = peaks[i];
      for (let j = Math.floor((i * length) / slices); j < end; j += 1) {
        const value = samples[j] < 0 ? -samples[j] : samples[j];
        if (value > peak) peak = value;
      }
      peaks[i] = peak;
    }
  }
  const loudest = Math.max(...peaks) || 1;
  return peaks.map((peak) => peak / loudest);
}

const clamp = (value, low, high) => Math.min(Math.max(value, low), high);
// Rounding to a step, to the nearest / down / up. The tiny nudges absorb float noise.
const snapTo = (value, step) => toMillis(Math.round(value / step) * step);
const snapDown = (value, step) => toMillis(Math.floor(value / step + 1e-6) * step);
const snapUp = (value, step) => toMillis(Math.ceil(value / step - 1e-6) * step);
const songEnd = (duration) => Math.floor(duration * 1000 + 1e-6) / 1000;

// A dragged range: both edges land on `step` (1 = whole seconds), inside the
// song, at least one step long and no longer than a single part may be.
// `anchor` says which edge stays put when the range has to shrink.
export function fitRange(start, end, duration, maxLength, anchor = "start", step = 1) {
  const shortest = Math.max(step, MIN_PART_SECONDS);
  const limit = Math.max(snapDown(songEnd(duration), step), shortest);
  let from = clamp(snapTo(Math.min(start, end), step), 0, limit - shortest);
  let to = clamp(snapTo(Math.max(start, end), step), from + shortest, limit);
  if (to - from > maxLength) {
    if (anchor === "end") from = to - maxLength;
    else to = from + maxLength;
  }
  return { start: toMillis(from), end: toMillis(to) };
}

// Moves one edge ("start" or "end") of a part to `time`, landing on `step`.
// The other edge is never touched, even if it was typed to the millisecond.
export function moveEdge(part, edge, time, duration, maxLength, step = 1) {
  const last = songEnd(duration);
  if (edge === "start") {
    const latest = Math.max(snapDown(part.end - MIN_PART_SECONDS, step), 0);
    const earliest = Math.min(Math.max(snapUp(part.end - maxLength, step), 0), latest);
    return { start: clamp(snapTo(time, step), earliest, latest), end: part.end };
  }
  const earliest = Math.min(snapUp(part.start + MIN_PART_SECONDS, step), last);
  const latest = Math.max(Math.min(snapDown(part.start + maxLength, step), snapDown(last, step)), earliest);
  return { start: part.start, end: clamp(snapTo(time, step), earliest, latest) };
}

// Moves a range without changing its length, stopping at the song's edges.
export function shiftRange(part, delta, duration, step = 1) {
  const length = toMillis(part.end - part.start);
  const start = clamp(snapTo(part.start + delta, step), 0, Math.max(toMillis(songEnd(duration) - length), 0));
  return { start, end: toMillis(start + length) };
}

export const partSeconds = (part) => Math.max(toMillis(part.end - part.start), 0);
export const totalSeconds = (parts) => toMillis(parts.reduce((sum, part) => sum + partSeconds(part), 0));

// Same rule as Simple mode and the server: started minutes plus a fee per part after the first.
export function proCost(parts, limits = DEFAULT_LIMITS) {
  if (!parts.length || parts.some((part) => partSeconds(part) <= 0)) return null;
  return Math.ceil(totalSeconds(parts) / 60) + (parts.length - 1) * limits.extra_track_credits;
}

export function validateFile(file, limits = DEFAULT_LIMITS) {
  if (!file) return "Choose an audio file.";
  if (!UPLOAD_EXTENSIONS.includes(fileExtension(file.name))) return "Use an MP3, WAV, M4A, AAC, OGG, OPUS, FLAC, WEBM or MP4 file.";
  if (!file.size) return "This file is empty.";
  if (file.size > limits.max_upload_bytes) return `This file is larger than ${megabytes(limits.max_upload_bytes)}.`;
  return "";
}

export const validateLink = (url) => (isYouTubeVideoUrl(String(url ?? "").trim()) ? "" : YOUTUBE_LINK_MESSAGE);

// { partErrors: { [part.id]: message }, formError: message }; both empty when ready to merge.
export function validatePro(songs, parts, options, limits = DEFAULT_LIMITS) {
  const byId = new Map(songs.map((song) => [song.id, song]));
  const partErrors = {};
  for (const part of parts) {
    const song = byId.get(part.songId);
    const length = partSeconds(part);
    let message = "";
    if (!song || song.status !== "ready") message = "This song isn't loaded.";
    else if (length < MIN_PART_SECONDS) message = `A part must be at least ${MIN_PART_SECONDS} seconds long.`;
    else if (length > limits.max_segment_seconds) message = `Each part can be at most ${Math.floor(limits.max_segment_seconds / 60)} minutes.`;
    else if (part.end > Math.floor(song.duration) + 1) message = `This song is only ${formatTime(Math.floor(song.duration))} long.`;
    else if (part.fadeIn + part.fadeOut > length) message = "The fades are longer than this part.";
    if (message) partErrors[part.id] = message;
  }
  const lengths = parts.map(partSeconds);
  const files = new Set(parts.map((part) => byId.get(part.songId)?.file).filter(Boolean));
  const uploadBytes = [...files].reduce((sum, file) => sum + file.size, 0);
  let formError = "";
  if (parts.length < MIN_TRACKS) formError = `Pick at least ${MIN_TRACKS} parts to merge.`;
  else if (parts.length > limits.max_tracks) formError = `You can merge at most ${limits.max_tracks} parts.`;
  else if (totalSeconds(parts) > limits.max_total_seconds) formError = `The merged song can be at most ${Math.floor(limits.max_total_seconds / 60)} minutes.`;
  else if (uploadBytes > limits.max_request_bytes) formError = `Uploaded files can total at most ${megabytes(limits.max_request_bytes)}.`;
  else if (options.crossfade && Math.min(...lengths) < options.crossfade * 2) {
    formError = "With a blend, every part must be at least twice as long as the blend.";
  }
  return { partErrors, formError };
}

// The merge API's request: one track per part. A file used by several parts is sent once.
export function buildProRequest(songs, parts, options) {
  const byId = new Map(songs.map((song) => [song.id, song]));
  const files = [];
  const spec = {
    tracks: parts.map((part) => {
      const song = byId.get(part.songId);
      const base = {
        start_time: part.start, end_time: part.end,
        volume: song.volume, fade_in: part.fadeIn, fade_out: part.fadeOut,
      };
      if (song.kind === "youtube") {
        return { source: "youtube", url: song.url, ...(song.sourceId ? { source_id: song.sourceId } : {}), ...base };
      }
      let index = files.indexOf(song.file);
      if (index < 0) index = files.push(song.file) - 1;
      return { source: "upload", file_index: index, ...base };
    }),
    output_format: options.outputFormat,
    crossfade_seconds: options.crossfade,
  };
  return { spec, files };
}

// Where `seconds` of the merged timeline falls: which part, and how far into it.
export function locateInSequence(parts, seconds) {
  let before = 0;
  for (let index = 0; index < parts.length; index += 1) {
    const length = partSeconds(parts[index]);
    if (seconds < before + length || index === parts.length - 1) {
      return { index, offset: Math.min(Math.max(seconds - before, 0), length) };
    }
    before += length;
  }
  return { index: 0, offset: 0 };
}

export const secondsBefore = (parts, index) => totalSeconds(parts.slice(0, index));

// How loud a part plays `at` seconds into the song: the song's volume, shaped by the part's fades.
export function previewGain(part, volume, at) {
  let gain = volume / 100;
  if (part.fadeIn && at - part.start < part.fadeIn) gain *= Math.max(at - part.start, 0) / part.fadeIn;
  if (part.fadeOut && part.end - at < part.fadeOut) gain *= Math.max(part.end - at, 0) / part.fadeOut;
  return Math.min(Math.max(gain, 0), 1);
}

// Seconds between ruler labels, so about one label fits every `spacing` pixels
// of a view that shows `duration` seconds (less than the whole song when zoomed).
export function rulerStep(duration, width, spacing = 70) {
  const steps = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  const wanted = (duration * spacing) / Math.max(width, 1);
  return steps.find((step) => step >= wanted) ?? steps[steps.length - 1];
}

// File extension for a recording, from the type the browser recorded in.
export function recordingExtension(mimeType) {
  const type = String(mimeType ?? "").toLowerCase();
  if (type.includes("mp4")) return ".m4a";
  if (type.includes("ogg")) return ".ogg";
  return ".webm";
}
