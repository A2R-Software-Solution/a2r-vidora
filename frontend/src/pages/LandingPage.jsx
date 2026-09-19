import { useEffect, useRef } from "react";
import Hero from "../components/landing/Hero";
import InputBox from "../components/landing/InputBox";
import YouTubeUnavailable from "../components/landing/YouTubeUnavailable";
import Features from "../components/landing/Features";
import { useVideoAnalyze } from "../hooks/useVideoAnalyze";
import { warmUpVideoAnalysis } from "../api/videoApi";

export default function LandingPage({ onAnalyzed, compact }) {
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
    <Hero compact={compact}>
      {youtubeUnavailable ? <YouTubeUnavailable onDismiss={dismissUnavailable} /> : <InputBox onAnalyze={handleAnalyze} loading={loading} restoring={restoring} error={error} onClearError={clearError} />}
      {hasPreviousVideo && !loading && !youtubeUnavailable && (
        <button className="resume-analysis" type="button" onClick={async () => {
          const recovered = await restoreVideo();
          if (recovered) onAnalyzed(recovered);
        }}>Resume previous analysis</button>
      )}
      <p className="hint">AI answers may be inaccurate. Verify important details against the video.
        Only submit content you have permission to process.</p>
      {!compact && <Features />}
    </Hero>
  );
}
