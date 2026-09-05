import { errorMessage } from "../api/errorMessage";
import { useState, useCallback } from "react";
import { askQuestion, getQaHistory } from "../api/videoApi";

const MAX_QUESTIONS = 5;

export function useVideoQA(videoId) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [historyCount, setHistoryCount] = useState(0);

  const fetchHistory = useCallback(async (signal) => {
    if (!videoId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getQaHistory(videoId, signal);
      if (signal?.aborted) return;
      setMessages([...response.data.items].reverse());
      setHistoryCount(response.data.total ?? response.data.items.length);
    } catch (err) {
      if (!signal?.aborted) setError(errorMessage(err, "Failed to load Q&A history"));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [videoId]);

  const askVideo = async (question) => {
    if (loading || !videoId) return;
    if (historyCount >= MAX_QUESTIONS) {
      setError(`You've reached the limit of ${MAX_QUESTIONS} questions.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await askQuestion(videoId, { question });
      setMessages((prev) => [...prev, response.data]);
      setHistoryCount((count) => count + 1);
      return response.data;
    } catch (err) {
      setError(errorMessage(err, "Failed to get answer"));
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return {
    messages,
    fetchHistory,
    askVideo,
    loading,
    error,
    questionCount: historyCount,
    limitReached: historyCount >= MAX_QUESTIONS,
  };
}