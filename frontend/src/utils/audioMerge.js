// Song Merger rules shared by the page and its tests. The server enforces the
// same limits (functions/app/schemas/audio_merge_schema.py); GET
// /audio-merges/limits supplies the real values, these are only the fallback.
import { formatTime } from "./formatTime.js";
import { CREDITS_MESSAGE, YOUTUBE_LINK_MESSAGE, isYouTubeVideoUrl } from "./videoInput.js";

export const songMergerMeta = {
  label: "Song Merger",
  description: "Join sections of YouTube videos and your own audio into one downloadable song with Vidora AI Song Merger.",
};

export const DEFAULT_LIMITS = Object.freeze({
  enabled: true,
  max_tracks: 10,
  max_segment_seconds: 600,
  max_total_seconds: 1800,
  max_upload_bytes: 10 * 1024 * 1024,
  max_request_bytes: 25 * 1024 * 1024,
  extra_track_credits: 1,
  max_crossfade_seconds: 10,
  output_formats: ["mp3", "m4a"],
});

export const MIN_TRACKS = 2;
export const UPLOAD_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".weba", ".webm", ".mp4"];
export const CROSSFADE_CHOICES = [0, 1, 2, 3, 5];

export const FAILURE_MESSAGES = {
  INVALID_RANGE: "A track's time range goes past the end of its source. Check the start and end times.",
  INVALID_AUDIO: "One of the uploaded files couldn't be read as audio.",
  QUEUE_UNAVAILABLE: "We couldn't start the merge. Your credits were returned. Please try again.",
  JOB_TIMED_OUT: "The merge took too long and was stopped. Your credits were returned.",
};

export const megabytes = (bytes) => `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;

// "1:30", "1:02:03" or plain seconds -> whole seconds, or null when unreadable.
export function parseTime(text) {
  const value = String(text ?? "").trim();
  if (/^\d{1,5}$/.test(value)) return Number(value);
  let match = value.match(/^(\d{1,3}):([0-5]?\d)$/);
  if (match) return Number(match[1]) * 60 + Number(match[2]);
  match = value.match(/^(\d{1,2}):([0-5]?\d):([0-5]?\d)$/);
  if (match) return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
  return null;
}

export function trackSeconds(track) {
  const start = parseTime(track.start);
  const end = parseTime(track.end);
  return start != null && end != null && end > start ? end - start : 0;
}

export const fileExtension = (name) => {
  const dot = String(name ?? "").lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
};

export function validateTrack(track, limits = DEFAULT_LIMITS) {
  if (track.source === "youtube") {
    if (!isYouTubeVideoUrl(track.url ?? "")) return YOUTUBE_LINK_MESSAGE;
  } else {
    const file = track.file;
    if (!file) return "Choose an audio file.";
    if (!UPLOAD_EXTENSIONS.includes(fileExtension(file.name))) return "Use an MP3, WAV, M4A, AAC, OGG, OPUS, FLAC, WEBM or MP4 file.";
    if (!file.size) return "This file is empty.";
    if (file.size > limits.max_upload_bytes) return `This file is larger than ${megabytes(limits.max_upload_bytes)}.`;
  }
  const start = parseTime(track.start);
  const end = parseTime(track.end);
  if (start == null) return "Enter a start time like 1:00.";
  if (end == null) return "Enter an end time like 2:40.";
  if (end <= start) return "The end time must be after the start time.";
  if (end - start > limits.max_segment_seconds) return `Each track can be at most ${Math.floor(limits.max_segment_seconds / 60)} minutes.`;
  if (track.source === "upload" && track.duration && end > Math.ceil(track.duration) + 1) {
    return `This file is only ${formatTime(Math.floor(track.duration))} long.`;
  }
  return "";
}

// { trackErrors: { [track.id]: message }, formError: message }; both empty when ready.
export function validateMerge(tracks, options, limits = DEFAULT_LIMITS) {
  const trackErrors = {};
  for (const track of tracks) {
    const message = validateTrack(track, limits);
    if (message) trackErrors[track.id] = message;
  }
  let formError = "";
  const lengths = tracks.map(trackSeconds);
  const total = lengths.reduce((sum, seconds) => sum + seconds, 0);
  const uploadBytes = tracks.reduce((sum, track) => sum + (track.source === "upload" ? track.file?.size ?? 0 : 0), 0);
  if (tracks.length < MIN_TRACKS) formError = `Add at least ${MIN_TRACKS} tracks.`;
  else if (tracks.length > limits.max_tracks) formError = `You can merge at most ${limits.max_tracks} tracks.`;
  else if (total > limits.max_total_seconds) formError = `The merged song can be at most ${Math.floor(limits.max_total_seconds / 60)} minutes.`;
  else if (uploadBytes > limits.max_request_bytes) formError = `Uploaded files can total at most ${megabytes(limits.max_request_bytes)}.`;
  else if (options.crossfade && Math.min(...lengths) < options.crossfade * 2) {
    formError = "With a crossfade, every track must be at least twice as long as the crossfade.";
  }
  return { trackErrors, formError };
}

// Mirrors audio_merge_credit_cost on the server; null until every track has a valid range.
export function mergeCost(tracks, limits = DEFAULT_LIMITS) {
  const lengths = tracks.map(trackSeconds);
  if (!lengths.length || lengths.some((seconds) => seconds <= 0)) return null;
  return Math.ceil(lengths.reduce((sum, seconds) => sum + seconds, 0) / 60) +
    (lengths.length - 1) * limits.extra_track_credits;
}

export function buildMergeRequest(tracks, options) {
  const files = [];
  const spec = {
    tracks: tracks.map((track) => {
      const base = { source: track.source, start_time: parseTime(track.start), end_time: parseTime(track.end) };
      if (track.source === "youtube") return { ...base, url: track.url.trim() };
      return { ...base, file_index: files.push(track.file) - 1 };
    }),
    output_format: options.outputFormat,
    crossfade_seconds: options.crossfade,
  };
  return { spec, files };
}

export const isMergePending = (job) => job.status === "queued" || job.status === "processing";
export const isMergeExpired = (job, now = Date.now()) => job.status === "expired" ||
  (Number.isFinite(Date.parse(job.expires_at)) && Date.parse(job.expires_at) <= now);

export function mergeFailureMessage(code) {
  return FAILURE_MESSAGES[code] ?? "The merge failed and its credits were returned. Please try again.";
}

// Never renders server text that may be an object (validation errors are arrays).
export function mergeError(error) {
  const { status, data } = error?.response ?? {};
  if (status === 402) return CREDITS_MESSAGE;
  if (status === 503) return "Song Merger isn't available yet.";
  if (status === 413) return "Your files are too large. Use smaller files.";
  if (status === 429) return "Too many requests. Wait a while before trying again.";
  if (status === 404) return "This merge could not be found.";
  if (status === 410) return "This merge has expired. Create it again to get a fresh download.";
  if ((status === 415 || status === 422) && typeof data?.detail === "string" && data.detail.length < 300) return data.detail;
  if (status === 422) return "Please check your tracks and try again.";
  if (error?.code === "ERR_NETWORK") return "We couldn't connect. Check your internet connection and try again.";
  if (["ECONNABORTED", "ETIMEDOUT"].includes(error?.code)) return "The upload took too long. Try smaller files.";
  return "We couldn't complete that request. Please try again.";
}
