import { useState, useEffect } from "react";
import { useVideoQA } from "../../hooks/useVideoQA";
import MessageBubble from "./MessageBubble";
import TimestampChip from "./TimestampChip";

export default function ChatPanel({ videoId, onSeek }) {
  const { messages, fetchHistory, askVideo, loading, error } = useVideoQA(videoId);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleAsk = async () => {
    const trimmed = question.trim();
    if (!trimmed) return;
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
        <span className="chat-tab new-video">↻ New Video</span>
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

      <div className="ask">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask another question..."
          disabled={loading}
        />
        <button className="send" onClick={handleAsk} disabled={loading}>↑</button>
      </div>
    </div>
  );
}