import { useState, useEffect } from "react";
import { useVideoQA } from "../../hooks/useVideoQA";
import MessageBubble from "./MessageBubble";
import TimestampChip from "./TimestampChip";
import YouTubeUnavailable from "../landing/YouTubeUnavailable";
import SiteLink from "../common/SiteLink";
import { useCredits } from "../../hooks/useCredits";
import { QUESTIONS_MESSAGE, analysisFailure } from "../../utils/videoInput";

import { config } from "../../config";
const MAX_CHARS = config.maxQuestionChars;

export default function ChatPanel({ videoId, videoTitle, youtubeUrl, onSeek, ready = true, progress, active = true, onSignIn, signedIn = false }) {
  const { messages, fetchHistory, askVideo, loading, error } = useVideoQA(videoId);
  const credits = useCredits();
  // Unknown (null) while the balance loads or on an older backend: allow asking.
  const questionsLeft = credits?.questions_left ?? null;
  const limitReached = questionsLeft === 0;
  const [question, setQuestion] = useState("");
  const [charError, setCharError] = useState("");
  const failed = progress?.status === "failed";
  const cookieFailure = failed && progress?.processing_stage === "youtube_session_unavailable";
  const failure = failed ? analysisFailure(progress?.processing_stage, signedIn) : null;

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
    // The hook shows the error; nothing else to do here.
    await askVideo(trimmed).catch(() => {});
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleAsk();
  };

  const downloadHistory = () => {
    const entries = messages.map((message, index) => [
      `Question ${index + 1}: ${message.question}`,
      `Answer: ${message.answer}`,
      message.created_at ? `Asked: ${new Date(message.created_at).toLocaleString()}` : null,
    ].filter(Boolean).join("\n")).join("\n\n");
    const content = [
      "Vidora AI - Video Q&A history",
      `Video: ${videoTitle || "Untitled video"}`,
      youtubeUrl ? `Source: ${youtubeUrl}` : null,
      `Downloaded: ${new Date().toLocaleString()}`,
      "",
      entries,
      "",
    ].filter(Boolean).join("\n");
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "vidora-video-qa.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="chat">
      <div className="chat-tabs">
        <span className="chat-tab active">✨ AI Answer</span>
        <span className="chat-tab">💬 Chat</span>
        <span className="question-counter">
          {questionsLeft === null ? `${messages.length} questions` : `${questionsLeft} questions left today`}
        </span>
        {messages.length > 0 && <button type="button" className="download-history" onClick={downloadHistory}>Download Q&A</button>}
      </div>

      {!ready && cookieFailure && <YouTubeUnavailable onDismiss={() => window.location.reload()} active={active} />}
      {!ready && !cookieFailure && <div className="messages"><div className="message ai"><b>{failed ? "We couldn't process this video" : "Processing your video"}</b><br />
        {failed ? <>
          {failure.text}
          {(failure.pricing || failure.signIn) && <br />}
          {failure.pricing && <SiteLink className="duration-sign-in" href="/pricing">See pricing</SiteLink>}
          {failure.signIn && <button type="button" className="duration-sign-in" onClick={onSignIn}>Sign in</button>}
        </> : <>
          {progress?.processing_stage === "queued" && "Your analysis is queued."}
          {progress?.processing_stage === "download" && "Downloading and preparing audio."}
          {progress?.processing_stage === "vad_chunking" && "Detecting speech and creating audio chunks."}
          {progress?.processing_stage === "chunk_transcription" && `Transcribing audio (${progress?.processing_completed_chunks || 0}/${progress?.processing_total_chunks || 0} requests complete).`}
          {progress?.processing_stage === "waiting_for_quota" && "Waiting for transcription capacity. Your completed audio is saved."}
          {progress?.processing_stage === "embed" && "Making the transcript searchable."}
          {progress?.processing_stage === "summarize" && "Generating the video summary."}
          {progress?.processing_stage === "persist" && "Saving your analysis."}
        </>}
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

      {error && !limitReached && <div className="error-text">{error}</div>}
      {charError && <div className="error-text">{charError}</div>}

      {!ready ? <div className="ask-hint">Questions unlock automatically when analysis is complete.</div> : limitReached ? (
        <div className="limit-reached-text">
          {QUESTIONS_MESSAGE}
          {!credits?.is_paid && <> <SiteLink href="/pricing">Credit packs include more questions.</SiteLink></>}
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
