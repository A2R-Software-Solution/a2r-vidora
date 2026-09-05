import { errorMessage } from "../api/errorMessage";
import { useState } from "react";
import { analyzeVideo, getVideos } from "../api/videoApi";

// localStorage key jahan hum current video_id save karte hain, taaki
// page refresh hone par Workspace restore ho sake.
const VIDEO_ID_STORAGE_KEY = "vidora_video_id";

// Polling settings: har 3 second me status check karenge, max 60 tries
// (yaani ~3 minute) ke baad polling ruk jayegi taaki infinite loop na bane.
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_ATTEMPTS = 60;

// Chhota helper: given ms, ek promise return karta hai jo utni der baad resolve hoga.
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function useVideoAnalyze() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [video, setVideo] = useState(null);

  // Given video_id, /videos?video_id=... call karke us specific video ko
  // dhoondta hai. Ye anonymous user ke liye bhi kaam karta hai (poori list
  // wala /videos call sirf logged-in user ke liye allowed hai, 401 deta
  // hai anonymous ke liye).
  const findVideoById = async (videoId) => {
    try {
      const response = await getVideos(videoId);
      const videos = response.data || [];
      return videos[0] || null;
    } catch (err) {
      if (err?.response?.status === 404 || err?.response?.status === 410) {
        // Video nahi mila (404) ya expire ho kar cleanup job se delete
        // ho chuka hai (410) - dono case me null treat karo.
        return null;
      }
      throw err;
    }
  };

  // Video ka status "processing" na rahe tab tak har POLL_INTERVAL_MS
  // par getVideos() call karke check karta rehta hai.
  const pollVideoStatus = async (videoId) => {
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      const foundVideo = await findVideoById(videoId);

      if (!foundVideo) {
        // Video list me nahi mila (shayad delete ho gaya ya id galat hai).
        setError("Video not found");
        return null;
      }

      if (foundVideo.status === "completed" || foundVideo.status === "failed") {
        setVideo(foundVideo);
        return foundVideo;
      }

      // Abhi bhi "processing" hai, thoda ruk kar phir try karenge.
      await wait(POLL_INTERVAL_MS);
    }

    // Max attempts khatam ho gaye, lekin video abhi bhi processing me hai.
    setError("Video is taking longer than expected to process");
    return null;
  };

  const submitVideo = async (youtubeUrl) => {
    setLoading(true);
    setError(null);
    try {
      const response = await analyzeVideo({ youtube_url: youtubeUrl });
      const newVideo = response.data;
      setVideo(newVideo);

      // video_id ko localStorage me save karo taaki refresh ke baad
      // restore kiya ja sake.
      localStorage.setItem(VIDEO_ID_STORAGE_KEY, newVideo.id);

      // Agar video abhi bhi "processing" state me hai, toh polling shuru
      // karo jab tak completed/failed na ho jaye.
      if (newVideo.status === "processing") {
        const finalVideo = await pollVideoStatus(newVideo.id);
        return finalVideo || newVideo;
      }

      return newVideo;
    } catch (err) {
      setError(errorMessage(err, "Failed to analyze video"));
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Page load par localStorage se saved video_id nikal kar, /videos list
  // se match karke video restore karta hai. Agar id nahi mila (expired ho
  // gaya ya delete ho gaya), toh localStorage se bhi clear kar deta hai.
  const restoreVideo = async () => {
    const savedVideoId = localStorage.getItem(VIDEO_ID_STORAGE_KEY);

    if (!savedVideoId) {
      return null;
    }

    setLoading(true);
    setError(null);
    try {
      const foundVideo = await findVideoById(savedVideoId);

      if (!foundVideo) {
        // Saved id ab valid nahi hai, stale entry hata do.
        localStorage.removeItem(VIDEO_ID_STORAGE_KEY);
        return null;
      }

      if (foundVideo.status === "failed") {
        // Pichla analysis fail ho gaya tha, isse restore karne ka koi
        // matlab nahi - stale entry hata kar Landing page hi dikhao.
        localStorage.removeItem(VIDEO_ID_STORAGE_KEY);
        return null;
      }

      setVideo(foundVideo);

      // Agar restore ke time video abhi bhi "processing" hai, toh polling
      // continue karo jab tak completed/failed na ho jaye.
      if (foundVideo.status === "processing") {
        const finalVideo = await pollVideoStatus(foundVideo.id);
        return finalVideo || foundVideo;
      }

      return foundVideo;
    } catch (err) {
      setError(errorMessage(err, "Failed to restore video"));
      return null;
    } finally {
      setLoading(false);
    }
  };

  return { submitVideo, restoreVideo, video, loading, error };
}