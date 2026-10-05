export const clipKey = (clip) => `${clip.start_time}-${clip.end_time}`;
export const isShortPending = (job) => job.status === "queued" || job.status === "rendering";
export const isShortExpired = (job, now = Date.now()) => job.status === "expired" ||
  (Number.isFinite(Date.parse(job.expires_at)) && Date.parse(job.expires_at) <= now);

export function shortCards(suggestions, jobs) {
  const byRange = new Map(jobs.map((job) => [clipKey(job), job]));
  const cards = suggestions.map((idea) => ({ ...idea, job: byRange.get(clipKey(idea)) }));
  const ideaKeys = new Set(suggestions.map(clipKey));
  for (const job of jobs) {
    if (!ideaKeys.has(clipKey(job))) cards.push({ ...job, title: "Your Short", job });
  }
  return cards;
}

export function shortError(error) {
  const status = error?.response?.status;
  if (status === 404) return "Short creation isn't available on this server yet.";
  if (status === 410) return "This video or Short has expired. Analyze the video again to continue.";
  if (status === 401 || status === 403) return "Sign in to the account that owns this video to access its Shorts.";
  if (status === 429) return "Too many requests. Wait a while before trying again.";
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.length < 300) return detail;
  return "We couldn't complete that request. Please try again.";
}
