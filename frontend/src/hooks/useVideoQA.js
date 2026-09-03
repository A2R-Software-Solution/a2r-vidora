import { useState, useCallback } from "react";
import { askQuestion, getQaHistory } from "../api/videoApi";

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
      setError(err?.response?.data?.detail || "Failed to load Q&A history");
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
      setError(err?.response?.data?.detail || "Failed to get answer");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return { messages, fetchHistory, askVideo, loading, error };
}