import { useState, useCallback } from "react";
import { askQuestion, getQaHistory } from "../api/videoApi";
import { friendlyApiError } from "../utils/videoInput";

import { config } from "../config";
const SIGNED_IN_QUESTION_LIMIT = 15;
const getQuestionLimit = (signedIn) => signedIn
  ? SIGNED_IN_QUESTION_LIMIT
  : config.maxQuestions;

export function useVideoQA(videoId, signedIn = false) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const questionLimit = getQuestionLimit(signedIn);

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
    if (messages.length >= questionLimit) {
      setError(`You've reached the limit of ${questionLimit} questions.`);
      return;
    }
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
    }
  };

  return {
    messages,
    fetchHistory,
    askVideo,
    loading,
    error,
    questionCount: messages.length,
    questionLimit,
    limitReached: messages.length >= questionLimit,
  };
}
