import apiClient from "./client";

export const analyzeVideo = (payload) => {
  return apiClient.post("/videos/analyze", payload);
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

export const getQaHistory = (videoId, signal) => {
  return apiClient.get(`/videos/${videoId}/qa`, { signal });
};