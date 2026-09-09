import { useRef, useState } from "react";
import { analyzeVideo, getVideos } from "../api/videoApi";

const VIDEO_ID_STORAGE_KEY = "vidora_video_id";
const PENDING_KEY = "vidora_pending_analysis";

export function useVideoAnalyze() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [video, setVideo] = useState(null);
  const submitting = useRef(false);

  const submitVideo = async (youtubeUrl) => {
    if (submitting.current) throw new Error("Analysis is already running.");
    submitting.current = true;
    setLoading(true);
    setError(null);
    try {
      let pending;
      try { pending = JSON.parse(localStorage.getItem(PENDING_KEY)); } catch { /* discard corrupt metadata */ }
      if (!pending || pending.url !== youtubeUrl || !pending.id) {
        pending = { id: crypto.randomUUID(), url: youtubeUrl };
        localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
      }
      localStorage.setItem(VIDEO_ID_STORAGE_KEY, pending.id);
      const { data } = await analyzeVideo({ youtube_url: youtubeUrl }, pending.id);
      if (data.status !== "completed") {
        throw new Error("Analysis is not ready. Please try again later.");
      }
      setVideo(data);
      localStorage.setItem(VIDEO_ID_STORAGE_KEY, data.id);
      localStorage.removeItem(PENDING_KEY);
      return data;
    } catch (err) {
      const detail = err?.response?.data?.detail;
      // A failed idempotent job cannot be resumed. Remove only its local key so
      // the user's next explicit click creates a new job. Do not auto-retry:
      // retrying could create unexpected paid AI work.
      if (err?.response?.status === 409 && detail === "This submission previously failed. You can submit it again.") {
        localStorage.removeItem(PENDING_KEY);
        localStorage.removeItem(VIDEO_ID_STORAGE_KEY);
        setError("Previous analysis failed. Please click Analyze Video again to start a new attempt.");
      } else {
        setError(detail || err.message || "Analysis failed.");
      }
      throw err;
    } finally {
      submitting.current = false;
      setLoading(false);
    }
  };

  // Restore is one read on demand, never a recurring status poll.
  const restoreVideo = async () => {
    const id = localStorage.getItem(VIDEO_ID_STORAGE_KEY);
    if (!id) return null;
    setLoading(true);
    setError(null);
    try {
      const { data } = await getVideos(id);
      const restored = data?.[0];
      if (restored?.status === "processing") {
        setError("Analysis is still running. You can check again later.");
        return null;
      }
      if (restored?.status !== "completed") {
        setError("Previous analysis failed or expired. You can submit it again.");
        localStorage.removeItem(PENDING_KEY);
        localStorage.removeItem(VIDEO_ID_STORAGE_KEY);
        return null;
      }
      setVideo(restored);
      localStorage.removeItem(PENDING_KEY);
      return restored;
    } catch (err) {
      if ([404, 410].includes(err?.response?.status)) {
        localStorage.removeItem(VIDEO_ID_STORAGE_KEY);
      } else {
        setError("Could not restore the previous video.");
      }
      return null;
    } finally {
      setLoading(false);
    }
  };

  return { submitVideo, restoreVideo, video, loading, error };
}
