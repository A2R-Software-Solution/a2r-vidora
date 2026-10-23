import { useEffect, useRef, useState } from "react";
import VideoPlayer from "../components/workspace/VideoPlayer";
import ChatPanel from "../components/workspace/ChatPanel";
import ShortSuggestions from "../components/workspace/ShortSuggestions";
import SiteLink from "../components/common/SiteLink";
import { getVideos } from "../api/videoApi";
import { refreshCredits } from "../hooks/useCredits";
import { analysisFailure } from "../utils/videoInput";

export default function WorkspacePage({ video, active = true, onSignIn, signedIn = false, mode = "analyze" }) {
  const reels = mode === "reels";
  const [hasOpenedReels, setHasOpenedReels] = useState(reels);
  const [hasOpenedAnalysis, setHasOpenedAnalysis] = useState(!reels);
  if (reels && !hasOpenedReels) setHasOpenedReels(true);
  if (!reels && !hasOpenedAnalysis) setHasOpenedAnalysis(true);
  const playerRef = useRef(null);
  const [previousVideo, setPreviousVideo] = useState(video);
  const [currentVideo, setCurrentVideo] = useState(video);

  // Reset only for a newly supplied analysis, not when the reading page changes.
  if (video !== previousVideo) {
    setPreviousVideo(video);
    setCurrentVideo(video);
  }

  useEffect(() => {
    if (!active || currentVideo?.status !== "processing") return undefined;
    const timer = setInterval(async () => {
      try {
        const { data } = await getVideos(currentVideo.id);
        if (data?.[0]) setCurrentVideo(data[0]);
        // Finishing settles or refunds the video's credits.
        if (data?.[0] && data[0].status !== "processing") void refreshCredits();
      } catch { /* The next poll can recover a transient network error. */ }
    }, 3000);
    return () => clearInterval(timer);
  }, [active, currentVideo?.id, currentVideo?.status]);

  useEffect(() => {
    if (!active) playerRef.current?.pause();
  }, [active]);

  useEffect(() => { playerRef.current?.pause(); }, [mode]);

  const failure = currentVideo?.status === "failed" ? analysisFailure(currentVideo.processing_stage, signedIn) : null;

  const handleSeek = (seconds) => {
    playerRef.current?.seekTo(seconds);
  };

  return (
    <section className="preview">
      <div className="workspace-tagline workspace-tagline-left" aria-hidden="true" hidden={reels}>
        Video, transcript<br />and AI — all in<br />one place.
      </div>
      <div className="workspace-tagline workspace-tagline-top-right" aria-hidden="true" hidden={reels}>
        ...to answers<br />in seconds.
        <svg className="tagline-arrow" viewBox="0 0 60 50" fill="none">
          <path d="M5 5 Q 30 10, 40 40" stroke="#ff6b35" strokeWidth="2" strokeLinecap="round"/>
          <path d="M32 34 L40 40 L34 28" stroke="#ff6b35" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="workspace-tagline workspace-tagline-bottom-right" aria-hidden="true" hidden={reels}>
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
            title={currentVideo?.title}
            duration={currentVideo?.duration}
            status={currentVideo?.status}
            youtubeUrl={currentVideo?.youtube_url}
          />
          <div className="workspace-side">
            {hasOpenedAnalysis && <div hidden={reels} inert={reels}>
              {currentVideo?.status === "completed" && <section className="workspace-summary" aria-labelledby="summary-heading">
                <h2 id="summary-heading">Video summary</h2>
                <p>{currentVideo.summary || "No summary is available for this video. You can still ask questions below."}</p>
              </section>}
              <ChatPanel videoId={currentVideo?.id} videoTitle={currentVideo?.title} youtubeUrl={currentVideo?.youtube_url} onSeek={handleSeek} ready={currentVideo?.status === "completed"} progress={currentVideo} active={active && !reels} onSignIn={onSignIn} signedIn={signedIn} />
            </div>}
            {hasOpenedReels && <div hidden={!reels} inert={!reels}>
              {currentVideo?.status === "completed" ? <ShortSuggestions key={currentVideo.id} videoId={currentVideo.id} onSeek={handleSeek} active={active && reels} /> :
                <div className="reel-preparation" role="status">
                  <h2>{currentVideo?.status === "failed" ? "Couldn't prepare this video" : "Preparing your video"}</h2>
                  <p>{failure ? failure.text : "We're processing the video's audio to find moments for your reel. Clip suggestions will unlock here when it's ready."}</p>
                  {failure?.pricing && <SiteLink className="duration-sign-in" href="/pricing">See pricing</SiteLink>}
                  {failure && !signedIn && <button type="button" className="duration-sign-in" onClick={onSignIn}>Sign in</button>}
                </div>}
            </div>}
          </div>
        </div>
      </div>
    </section>
  );
}
