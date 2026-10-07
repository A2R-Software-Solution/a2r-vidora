import { useEffect, useRef } from "react";
import InputBox from "../components/landing/InputBox";
import YouTubeUnavailable from "../components/landing/YouTubeUnavailable";
import { useVideoAnalyze } from "../hooks/useVideoAnalyze";
import { warmUpVideoAnalysis } from "../api/videoApi";

export default function LandingPage({ onAnalyzed, compact, active = true, mode = "analyze" }) {
  const reels = mode === "reels";
  const { submitVideo, restoreVideo, loading, restoring, hasPreviousVideo, error, clearError, youtubeUnavailable, dismissUnavailable } = useVideoAnalyze();
  const warmupStarted = useRef(false);

  useEffect(() => {
    if (warmupStarted.current) return;
    warmupStarted.current = true;

    // Fire-and-forget: a failed warm-up must never affect rendering or the
    // user's later analysis request.
    void warmUpVideoAnalysis().catch(() => {});
  }, []);

  const handleAnalyze = async (url) => {
    try {
      const video = await submitVideo(url);
      onAnalyzed(video);
    } catch {
      // error already set in hook, UI dikha dega
    }
  };

  return (
    <section className={`hero tool-hero${compact ? " tool-hero--compact" : ""}`}>
      <span className="badge">{reels ? "YOUR REEL STUDIO" : "YOUR VIDEO, EXPLAINED"}</span>
      <h1>{reels ? "Long video. Reel-worthy moments." : "Get to the heart of your video."}</h1>
      <p className="sub">{reels ? "Paste a YouTube link, prepare your video, then choose a suggested moment to create a captioned vertical reel." : "Paste a YouTube link for a summary and answers with timestamps. Explore the key points and ask your follow-up questions."}</p>
      {youtubeUnavailable ? <YouTubeUnavailable onDismiss={dismissUnavailable} active={active} /> : <InputBox mode={mode} onAnalyze={handleAnalyze} loading={loading} restoring={restoring} error={error} onClearError={clearError} />}
      {hasPreviousVideo && !loading && !youtubeUnavailable && (
        <button className="resume-analysis" type="button" onClick={async () => {
          const recovered = await restoreVideo();
          if (recovered) onAnalyzed(recovered);
        }}>{reels ? "Use previous video for reels" : "Resume previous analysis"}</button>
      )}
      <p className="hint">AI answers may be inaccurate. Verify important details against the video.
        Only submit content you have permission to process.</p>
    </section>
  );
}
