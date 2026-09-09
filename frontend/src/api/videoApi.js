import apiClient from "./client";

export const analyzeVideo = (payload, requestId) => {
  return apiClient.post("/videos/analyze", payload, {
    timeout: 310000,
    headers: { "Idempotency-Key": requestId },
  });
};

export const warmUpVideoAnalysis = () => {
  return apiClient.post("/videos/analyze", "", {
    params: { warmup: true },
    // A CORS-safelisted content type avoids an unnecessary preflight while
    // the backend ignores the warm-up body entirely.
    headers: { "Content-Type": "text/plain" },
    timeout: 10000,
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
