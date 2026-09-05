import { useState, useEffect } from "react";
import { useVideoQA } from "../../hooks/useVideoQA";
import MessageBubble from "./MessageBubble";
import SourceEvidence from "./SourceEvidence";
import IssueReport from "../governance/IssueReport";

const MAX_CHARACTERS = 2000;
const MAX_QUESTIONS = 5;

export default function ChatPanel({ videoId, onSeek }) {
  const { messages, fetchHistory, askVideo, loading, error, limitReached, questionCount } = useVideoQA(videoId);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchHistory(controller.signal);
    return () => controller.abort();
  }, [fetchHistory]);

  const handleAsk = async (event) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || limitReached || loading) return;
    try {
      const answer = await askVideo(trimmed);
      if (answer) setQuestion("");
    } catch {
      // Keep the draft for retry; the hook exposes a safe, user-facing error.
    }
  };

  return (
    <div className="chat">
      <div className="chat-tabs">
        <span className="chat-tab active">AI answers</span>
        <span className="question-counter">{questionCount}/{MAX_QUESTIONS} questions</span>
      </div>
      <p className="ai-notice">Answers can be incorrect. Compare the retrieved excerpts with the original video.
        A source excerpt is context for the model, not independent verification of its answer.</p>
      <div className="messages" aria-label="Question and answer history" aria-busy={loading}>
        {!messages.length && !loading && <p className="ai-notice">Ask a question about this video to get started.</p>}
        {messages.map((msg) => (
          <div key={msg.id} className="qa-exchange">
            <MessageBubble role="user" text={msg.question} />
            <MessageBubble role="ai" text={msg.answer}>
              <SourceEvidence sources={msg.sources} onSeek={onSeek} />
              <IssueReport videoId={videoId} answerId={msg.id} />
            </MessageBubble>
          </div>
        ))}
      </div>
      <div role="status">{loading && <p className="ai-notice">Loading AI answers…</p>}</div>
      {error && <div className="error-text" role="alert">{error}</div>}
      {limitReached ? (
        <div className="limit-reached-text">You've reached the question limit for this video.</div>
      ) : (
        <>
          <form className="ask" onSubmit={handleAsk}>
            <input value={question} dir="auto" aria-label="Question about the video"
              aria-describedby="question-hint" maxLength={MAX_CHARACTERS}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about this video..." disabled={loading} />
            <button className="send" type="submit" aria-label="Ask question" disabled={loading || !question.trim()}>↑</button>
          </form>
          <div className="ask-hint" id="question-hint">Up to {MAX_CHARACTERS} characters. Avoid sensitive personal information.</div>
        </>
      )}
    </div>
  );
}
