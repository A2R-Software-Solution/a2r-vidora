import { useState, useEffect } from "react";
import { useVideoQA } from "../../hooks/useVideoQA";
import MessageBubble from "./MessageBubble";
import TimestampChip from "./TimestampChip";

import { config } from "../../config";
const MAX_CHARS = config.maxQuestionChars;

export default function ChatPanel({ videoId, onSeek, ready = true, progress }) {
  const { messages, fetchHistory, askVideo, loading, error, limitReached, questionCount } = useVideoQA(videoId);
  const [question, setQuestion] = useState("");
  const [charError, setCharError] = useState("");

  useEffect(() => {
    if (ready) fetchHistory();
  }, [fetchHistory, ready]);

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
        <span className="question-counter">{questionCount}/{config.maxQuestions} questions</span>
      </div>

      {!ready && <div className="messages"><div className="message ai"><b>Processing your video</b><br />
        {progress?.processing_stage === "queued" && "Your analysis is queued."}
        {progress?.processing_stage === "download" && "Downloading and preparing audio."}
        {progress?.processing_stage === "vad_chunking" && "Detecting speech and creating audio chunks."}
        {progress?.processing_stage === "chunk_transcription" && `Transcribing ${progress?.processing_total_chunks || 0} speech chunks in parallel.`}
        {progress?.processing_stage === "embed" && "Making the transcript searchable."}
        {progress?.processing_stage === "summarize" && "Generating the video summary."}
        {progress?.processing_stage === "persist" && "Saving your analysis."}
      </div></div>}
      {ready && <div className="messages">
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
      </div>}

      {error && <div className="error-text">{error}</div>}
      {charError && <div className="error-text">{charError}</div>}

      {!ready ? <div className="ask-hint">Questions unlock automatically when analysis is complete.</div> : limitReached ? (
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
