import { useState, useCallback } from "react";
import { askQuestion, getQaHistory } from "../api/videoApi";
import { friendlyApiError } from "../utils/videoInput";
import { refreshCredits } from "./useCredits";

// Question limits are daily and per account; the backend enforces them and
// GET /credits reports what is left (see useCredits).
export function useVideoQA(videoId) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchHistory = useCallback(async () => {
    if (!videoId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getQaHistory(videoId);
      setMessages(response.data.items);
    } catch (err) {
      setError(friendlyApiError(err, "qa"));
    } finally {
      setLoading(false);
    }
  }, [videoId]);

  const askVideo = async (question) => {
    setLoading(true);
    setError(null);
    try {
      const response = await askQuestion(videoId, { question });
      setMessages((prev) => [...prev, response.data]);
      return response.data;
    } catch (err) {
      setError(friendlyApiError(err, "qa"));
      throw err;
    } finally {
      setLoading(false);
      void refreshCredits();
    }
  };

  return { messages, fetchHistory, askVideo, loading, error };
}
