export const YOUTUBE_LINK_MESSAGE = "Please paste a valid YouTube video link (youtube.com/watch?v=… or youtu.be/…).";

export function isYouTubeVideoUrl(value) {
  const input = value.trim();
  if (!input || input.length > 500 || /[\s\\]/u.test(input)) return false;
  try {
    const url = new URL(input);
    if (!input.toLowerCase().startsWith("https://") || url.protocol !== "https:" || url.username || url.password || url.port) return false;
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname)) return false;
    const id = url.hostname === "youtu.be" ? url.pathname.slice(1)
      : url.pathname === "/watch" ? url.searchParams.get("v") : null;
    return /^[a-zA-Z0-9_-]{11}$/.test(id ?? "");
  } catch {
    return false;
  }
}

// API details can contain internal text or objects. Only display our own copy.
export function friendlyApiError(error, context = "analyze") {
  const status = error?.response?.status;
  if (["ECONNABORTED", "ETIMEDOUT"].includes(error?.code)) return "This is taking longer than expected. Please try again in a moment.";
  if (error?.code === "ERR_NETWORK") return "We couldn’t connect. Please check your internet connection and try again.";
  if (status === 429) return "Too many requests right now. Please wait a moment and try again.";
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You don’t have access to this video. Please try another video.";
  if (status === 404 || status === 410) return "This video or analysis is no longer available. Please submit a YouTube video link again.";
  if (status === 409) return "Your previous analysis may still be running. Please wait a moment, then use Resume previous analysis.";
  if (status === 400 || status === 422) return context === "analyze" ? YOUTUBE_LINK_MESSAGE : "We couldn’t process that request. Please check your input and try again.";
  if (status === 504) return "This video took too long to process. Please try a shorter YouTube video.";
  if (status >= 500) return "Our system couldn’t complete your request right now. Please try again in a few moments.";
  return context === "analyze" ? "We couldn’t analyze this video. Please try again with a public YouTube video up to 35 minutes long."
    : "We couldn’t complete your request. Please try again in a moment.";
}
