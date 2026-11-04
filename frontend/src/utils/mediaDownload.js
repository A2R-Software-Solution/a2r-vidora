export const downloaderMeta = {
  label: "Media Downloader",
  description: "Download audio or video from your own YouTube content in the quality you choose, with Vidora AI Media Downloader.",
};

export const OWNERSHIP_TEXT =
  "I confirm this is my own content, or I have the right to download it. I will use the file only as the law and the source's terms allow.";

export const RIGHTS_WARNING =
  "Only download content you created or have permission to download. Downloads are for your own content. Vidora does not check ownership, and you are responsible for how you use the file.";

const ACTIVE = new Set(["queued", "processing"]);

export const isDownloadActive = (job) => ACTIVE.has(job?.status);

export function downloadCost(options, code) {
  return options?.find((option) => option.code === code)?.credit_cost ?? null;
}

export function groupQualities(qualities = []) {
  return {
    audio: qualities.filter((quality) => quality.kind === "audio"),
    video: qualities.filter((quality) => quality.kind === "video"),
  };
}

export const FAILURE_MESSAGES = {
  YOUTUBE_BLOCKED: "YouTube is temporarily blocking downloads. Your credits were returned.",
  UNSUPPORTED_MEDIA: "This video can't be downloaded (live, upcoming, or too long). Your credits were returned.",
  DOWNLOAD_FAILED: "We could not download this video. Your credits were returned.",
  QUEUE_UNAVAILABLE: "The download queue is busy. Your credits were returned. Please try again.",
  JOB_TIMED_OUT: "The download took too long and was stopped. Your credits were returned.",
  expired: "This file has expired. Download it sooner next time.",
};

export function downloadFailureMessage(job) {
  return FAILURE_MESSAGES[job?.error_code] || FAILURE_MESSAGES[job?.status] || "This download did not finish. Please try again.";
}

export function downloadError(err) {
  const status = err?.response?.status;
  const data = err?.response?.data;
  if (status === 402) {
    return "You don't have enough download credits for this quality. Download credits renew at midnight IST, or you can get more credits.";
  }
  if (status === 429) return "Too many requests. Please wait a few minutes and try again.";
  if (status === 503 || status === 422) {
    if (typeof data?.detail === "string") return data.detail;
  }
  if (!err?.response) return "Network problem. Check your connection and try again.";
  return "Something went wrong. Please try again.";
}
