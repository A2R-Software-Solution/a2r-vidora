import { forwardRef, useEffect, useRef } from "react";
import { extractYouTubeId } from "../../utils/youtube";

const VideoPlayer = forwardRef(function VideoPlayer(
  { title, duration, status, youtubeUrl },
  ref
) {
  const playerRef = useRef(null);
  const videoId = extractYouTubeId(youtubeUrl);

  useEffect(() => {
    if (!videoId) return;

    function createPlayer() {
      playerRef.current = new window.YT.Player(`yt-player-${videoId}`, {
        videoId,
        playerVars: { rel: 0 },
      });
    }

    if (window.YT && window.YT.Player) {
      createPlayer();
    } else {
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      document.body.appendChild(tag);
      window.onYouTubeIframeAPIReady = createPlayer;
    }
  }, [videoId]);

  useEffect(() => {
    if (ref) {
      ref.current = {
        seekTo: (seconds) => {
          playerRef.current?.seekTo(seconds, true);
          playerRef.current?.playVideo();
        },
      };
    }
  }, [ref]);

  return (
    <div className="video">
      <div className="video-box">
        {videoId ? (
          <div id={`yt-player-${videoId}`} style={{ width: "100%", height: "100%" }} />
        ) : (
          <div className="play">▶</div>
        )}
      </div>
      <div className="video-title">{title || "Untitled video"}</div>
      <div className="video-meta">
        {duration ? `${duration} · ` : ""}{status || "Analyzed"}
      </div>
    </div>
  );
});

export default VideoPlayer;