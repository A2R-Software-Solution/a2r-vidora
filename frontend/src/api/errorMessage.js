// Never render arbitrary API payloads (validation details may include user input).
export function errorMessage(error, fallback) {
  const status = error?.response?.status;
  if (status === 503) return "AI processing is temporarily unavailable. Please try again later; this request did not complete.";
  if (status === 410) return "This video's analysis has expired. Analyze the video again to continue.";
  if (status === 403) return "You don't have access to this video.";
  if (status === 429) return "The request limit has been reached. Please wait before trying again.";
  if (status === 422) return "Please check your input and try again.";
  return fallback;
}
