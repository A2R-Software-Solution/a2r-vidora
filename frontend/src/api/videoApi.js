import apiClient from "./client";
import { config } from "../config";
import { getRecaptchaToken } from "../utils/recaptcha";

export const analyzeVideo = async (payload, requestId) => {
  const recaptchaToken = await getRecaptchaToken("analyze_video");
  return apiClient.post("/videos/analyze", payload, {
    timeout: config.analysisTimeoutMs,
    headers: {
      "Idempotency-Key": requestId,
      ...(recaptchaToken ? { "X-Recaptcha-Token": recaptchaToken } : {}),
    },
  });
};

export const warmUpVideoAnalysis = () => {
  return apiClient.post("/videos/analyze", "", {
    params: { warmup: true },
    // A CORS-safelisted content type avoids an unnecessary preflight while
    // the backend ignores the warm-up body entirely.
    headers: { "Content-Type": "text/plain" },
    // A cold model load plus the first database handshake can take longer than
    // 10 seconds.  This request is fire-and-forget, but it must be allowed to
    // complete so that the following analysis uses the warmed instance.
    timeout: config.warmupTimeoutMs,
  });
};

export const getVideos = (videoId) => {
  // Agar videoId diya gaya hai, toh single video fetch karo (backend
  // /videos?video_id=... support karta hai, anonymous user ke liye bhi
  // kaam karta hai). Videoid na diya ho toh poori list maangega, jo
  // sirf logged-in user ke liye allowed hai.
  if (videoId) {
    return apiClient.get("/videos", { params: { video_id: videoId } });
  }
  return apiClient.get("/videos");
};

export const askQuestion = (videoId, payload) => {
  return apiClient.post(`/videos/${videoId}/qa/ask`, payload);
};

export const getQaHistory = (videoId) => {
  return apiClient.get(`/videos/${videoId}/qa`);
};

export const suggestShorts = (videoId) => apiClient.post(`/videos/${videoId}/shorts/suggestions`);

export const createShort = (videoId, clip, options = {}) => apiClient.post(`/videos/${videoId}/shorts`, {
  start_time: clip.start_time,
  end_time: clip.end_time,
  ...options,
});
// The transcript captions of a clip, to edit before rendering (free).
export const getShortDraft = (videoId, clip, signal) => apiClient.get(`/videos/${videoId}/shorts/draft`, {
  params: { start_time: clip.start_time, end_time: clip.end_time }, signal,
});
// Fonts, ratios, presets and limits the editor offers; the server validates against the same lists.
export const getShortOptions = (signal) => apiClient.get("/shorts/options", { signal });
export const listShortPresets = () => apiClient.get("/shorts/presets");
export const createShortPreset = (name, style) => apiClient.post("/shorts/presets", { name, style });
export const deleteShortPreset = (presetId) => apiClient.delete(`/shorts/presets/${presetId}`);
export const getShort = (videoId, shortId, signal) => apiClient.get(`/videos/${videoId}/shorts/${shortId}`, { signal });
// Hindi (Devanagari) caption lines as Hinglish.
export const transliterateCaptions = (texts) => apiClient.post("/shorts/transliterate", { texts });
export const listShorts = (videoId, signal) => apiClient.get(`/videos/${videoId}/shorts`, { signal });
export const getShortDownload = (videoId, shortId, download = true) =>
  apiClient.get(`/videos/${videoId}/shorts/${shortId}/download`, { params: { download } });
