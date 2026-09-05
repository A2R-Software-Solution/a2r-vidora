import { useRef } from "react";
import VideoPlayer from "../components/workspace/VideoPlayer";
import ChatPanel from "../components/workspace/ChatPanel";

export default function WorkspacePage({ video }) {
  const playerRef = useRef(null);

  const handleSeek = (seconds) => {
    playerRef.current?.seekTo(seconds);
  };

  return (
    <section className="preview">
      <div className="workspace-tagline workspace-tagline-left" aria-hidden="true">
        Video, transcript<br />and AI — all in<br />one place.
      </div>
      <div className="workspace-tagline workspace-tagline-top-right" aria-hidden="true">
        ...to answers<br />in seconds.
        <svg className="tagline-arrow" viewBox="0 0 60 50" fill="none">
          <path d="M5 5 Q 30 10, 40 40" stroke="#ff6b35" strokeWidth="2" strokeLinecap="round"/>
          <path d="M32 34 L40 40 L34 28" stroke="#ff6b35" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="workspace-tagline workspace-tagline-bottom-right" aria-hidden="true">
        Actual answers.<br />Not just summaries.
        <svg className="tagline-arrow" viewBox="0 0 60 50" fill="none">
          <path d="M5 5 Q 30 10, 40 40" stroke="#ff6b35" strokeWidth="2" strokeLinecap="round"/>
          <path d="M32 34 L40 40 L34 28" stroke="#ff6b35" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="preview-card">
        <div className="window-dots">
          <span className="dot red"></span>
          <span className="dot yellow"></span>
          <span className="dot green"></span>
        </div>
        <div className="workspace">
          <VideoPlayer
            ref={playerRef}
            title={video?.title}
            duration={video?.duration}
            status={video?.status}
            youtubeUrl={video?.youtube_url}
          />
          <ChatPanel videoId={video?.id} onSeek={handleSeek} />
        </div>
      </div>
    </section>
  );
}