import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { extractYouTubeId } from "../../utils/youtube";
import { formatTime } from "../../utils/formatTime";

let youtubeReady;
function loadYouTube() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!youtubeReady) {
    youtubeReady = new Promise((resolve, reject) => {
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      tag.onerror = () => { youtubeReady = null; tag.remove(); reject(new Error("Player unavailable")); };
      document.body.appendChild(tag);
    });
  }
  return youtubeReady;
}

const VideoPlayer = forwardRef(function VideoPlayer({ title, duration, status, youtubeUrl }, ref) {
  const containerRef = useRef(null);
  const playerRef = useRef(null);
  const readyRef = useRef(false);
  const pendingSeek = useRef(null);
  const videoId = extractYouTubeId(youtubeUrl);

  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) return;
      if (readyRef.current) {
        playerRef.current.seekTo(seconds, true);
        playerRef.current.playVideo();
      } else {
        pendingSeek.current = seconds;
      }
    },
  }), []);

  useEffect(() => {
    if (!videoId) return;
    let disposed = false;
    let player;
    const container = containerRef.current;
    loadYouTube().then((YT) => {
      if (disposed) return;
      const mount = document.createElement("div");
      container.replaceChildren(mount);
      player = new YT.Player(mount, {
        videoId,
        playerVars: { rel: 0 },
        events: {
          onReady(event) {
            if (disposed) return;
            readyRef.current = true;
            event.target.getIframe().title = title || "Original YouTube video";
            if (pendingSeek.current !== null) {
              event.target.seekTo(pendingSeek.current, true);
              event.target.playVideo();
              pendingSeek.current = null;
            }
          },
        },
      });
      playerRef.current = player;
    }).catch(() => {
      if (!disposed) container.textContent = "Player unavailable. Use the original video link above.";
    });
    return () => {
      disposed = true;
      readyRef.current = false;
      pendingSeek.current = null;
      playerRef.current = null;
      player?.destroy();
    };
  }, [videoId, title]);

  return (
    <div className="video">
      <div className="video-box" ref={containerRef} />
      <div className="video-title" dir="auto">{title || "Untitled video"}</div>
      <div className="video-meta">{duration ? `${formatTime(duration)} · ` : ""}{status || "Analyzed"}</div>
    </div>
  );
});

export default VideoPlayer;
