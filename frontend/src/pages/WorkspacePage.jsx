import { useRef } from "react";
import VideoPlayer from "../components/workspace/VideoPlayer";
import ChatPanel from "../components/workspace/ChatPanel";
import IssueReport from "../components/governance/IssueReport";
import { extractYouTubeId } from "../utils/youtube";

export default function WorkspacePage({ video }) {
  const playerRef = useRef(null);
  const youtubeId = extractYouTubeId(video?.youtube_url);
  const expiry = video?.expires_at ? new Date(video.expires_at) : null;
  const expiryValid = expiry && Number.isFinite(expiry.getTime());
  const ready = video?.status === "completed";

  const handleSeek = (seconds) => {
    playerRef.current?.seekTo(seconds);
  };

  return (
    <section className="preview" aria-label="Video analysis workspace">
      <div className="preview-card">
        <div className="workspace-notice">
          <strong>Verify AI output against the source</strong>
          {youtubeId && <a href={`https://www.youtube.com/watch?v=${youtubeId}`} target="_blank" rel="noopener noreferrer">
            Open original video ↗</a>}
          {expiryValid && <p>Analysis expiry: <time dateTime={expiry.toISOString()}>{expiry.toLocaleString()}</time> (your local time).
            Expired analysis data is removed by scheduled cleanup.</p>}
        </div>
        <div className="workspace">
          <div>
            <VideoPlayer ref={playerRef} title={video?.title} duration={video?.duration}
              status={video?.status} youtubeUrl={video?.youtube_url} />
            {ready && video.summary && <section className="video-summary" aria-label="AI-generated summary">
              <h2>AI-generated summary</h2>
              <p className="ai-notice">This summary may cover only the beginning of a long video and may omit important context.
                Check the original video for the full account.</p>
              <p dir="auto" className="message-text">{video.summary}</p>
              <IssueReport videoId={video.id} outputType="summary" />
            </section>}
          </div>
          {ready ? <ChatPanel videoId={video.id} onSeek={handleSeek} /> : (
            <div className="chat" role="status">
              <h2>{video?.status === "failed" ? "Analysis couldn't be completed" : "Analysis isn't ready yet"}</h2>
              <p>{video?.status === "failed"
                ? "AI processing may be unavailable, or the video could not be processed. No completed analysis is available. Try again later."
                : "Processing is taking longer than expected. You can submit the link again later to start a new analysis."}</p>
              <p>You can still watch the original video.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
