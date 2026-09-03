import { useRef } from "react";
import VideoPlayer from "../components/workspace/VideoPlayer";
import ChatPanel from "../components/workspace/ChatPanel";
import ComingSoon from "../components/reels/ComingSoon";

export default function WorkspacePage({ video }) {
  const playerRef = useRef(null);

  const handleSeek = (seconds) => {
    playerRef.current?.seekTo(seconds);
  };

  return (
    <section className="preview">
      <div className="preview-card">
        <div className="preview-head">Workspace</div>
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
      <ComingSoon />
    </section>
  );
}