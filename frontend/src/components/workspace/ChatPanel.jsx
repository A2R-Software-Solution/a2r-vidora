import { useState, useEffect } from "react";
import { useVideoQA } from "../../hooks/useVideoQA";
import MessageBubble from "./MessageBubble";
import TimestampChip from "./TimestampChip";

const MAX_CHARS = 100;

export default function ChatPanel({ videoId, onSeek }) {
  const { messages, fetchHistory, askVideo, loading, error, limitReached, questionCount } = useVideoQA(videoId);
  const [question, setQuestion] = useState("");
  const [charError, setCharError] = useState("");

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleAsk = async () => {
    const trimmed = question.trim();
    if (!trimmed || limitReached) return;

    if (trimmed.length > MAX_CHARS) {
      setCharError(`Please keep questions under ${MAX_CHARS} characters.`);
      return;
    }

    setCharError("");
    setQuestion("");
    await askVideo(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleAsk();
  };

  return (
    <div className="chat">
      <div className="chat-tabs">
        <span className="chat-tab active">✨ AI Answer</span>
        <span className="chat-tab">💬 Chat</span>
        <span className="question-counter">{questionCount}/5 questions</span>
      </div>

      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={msg.id || idx}>
            <MessageBubble role="user" text={msg.question} />
            <MessageBubble role="ai" text={msg.answer}>
              {msg.start_time != null && (
                <TimestampChip
                  startSeconds={msg.start_time}
                  endSeconds={msg.end_time}
                  onClick={onSeek}
                />
              )}
            </MessageBubble>
          </div>
        ))}
      </div>

      {error && <div className="error-text">{error}</div>}
      {charError && <div className="error-text">{charError}</div>}

      {limitReached ? (
        <div className="limit-reached-text">
          You've asked {messages.length} questions — limit reached for this video.
        </div>
      ) : (
        <>
          <div className="ask">
            <input
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);
                if (charError) setCharError("");
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ask another question..."
              disabled={loading}
              maxLength={MAX_CHARS}
            />
            <button className="send" onClick={handleAsk} disabled={loading}>↑</button>
          </div>
          <div className="ask-hint">Keep your question under {MAX_CHARS} characters</div>
        </>
      )}
    </div>
  );
}