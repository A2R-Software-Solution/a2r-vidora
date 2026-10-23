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

export const CREDITS_MESSAGE = "You don't have enough credits for this. Free credits renew at midnight IST, or you can get more.";
export const QUESTIONS_MESSAGE = "You've used today's questions. They renew at midnight IST.";

// "credits" (402: balance too low), "questions" (daily question limit), or null.
export function creditProblem(error) {
  const { status, data } = error?.response ?? {};
  if (status === 402) return "credits";
  if (status === 429 && data?.code === "daily_question_limit") return "questions";
  return null;
}

// API details can contain internal text or objects. Only display our own copy.
export function friendlyApiError(error, context = "analyze") {
  if (isYouTubeSessionUnavailable(error)) return YOUTUBE_UNAVAILABLE_MESSAGE;
  const problem = creditProblem(error);
  if (problem === "credits") return CREDITS_MESSAGE;
  if (problem === "questions") return QUESTIONS_MESSAGE;
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
  return context === "analyze" ? "We couldn’t analyze this video. Please try again with a public YouTube video within your credits and duration limit."
    : "We couldn’t complete your request. Please try again in a moment.";
}


// Why a finished analysis failed, from the video's processing_stage.
// pricing: offer the pricing page; signIn: offer signing in.
export function analysisFailure(stage, signedIn) {
  if (stage === "insufficient_credits") return {
    text: "This video needs more credits than you have left (1 credit per minute). Free credits renew at midnight IST.",
    pricing: true, signIn: !signedIn,
  };
  if (stage === "no_speech") return {
    text: "We couldn't find any speech in this video, so there is nothing to summarize or search. The credits for this video were used.",
  };
  if (stage === "anonymous_duration_limit") return {
    text: "This video is longer than the 35-minute guest limit. Sign in to analyze longer videos, then submit it again.",
    signIn: true,
  };
  if (stage === "video_duration_limit") return { text: "This video exceeds the 3-hour limit." };
  return { text: "Please try again. If processing failed on our side, your credits were returned." };
}

export const YOUTUBE_UNAVAILABLE_MESSAGE = "Oops! YouTube access is temporarily unavailable. Please try again later. Report the issue and leave your email so we can follow up. Thanks for your support!";

export function isYouTubeSessionUnavailable(error) {
  return error?.response?.status === 503 &&
    error?.response?.data?.detail?.code === "YOUTUBE_SESSION_UNAVAILABLE";
}
