import { useEffect, useRef } from "react";
import Hero from "../components/landing/Hero";
import InputBox from "../components/landing/InputBox";
import Features from "../components/landing/Features";
import { useVideoAnalyze } from "../hooks/useVideoAnalyze";
import { warmUpVideoAnalysis } from "../api/videoApi";

export default function LandingPage({ onAnalyzed, compact }) {
  const { submitVideo, restoreVideo, loading, error } = useVideoAnalyze();
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
      <InputBox onAnalyze={handleAnalyze} loading={loading} />
      <button type="button" disabled={loading} onClick={async () => {
        const recovered = await restoreVideo();
        if (recovered) onAnalyzed(recovered);
      }}>Check previous analysis</button>
      <p className="hint">AI answers may be inaccurate. Verify important details against the video.
        Only submit content you have permission to process.</p>
      {error && <div className="error-text">{error}</div>}
      {!compact && <Features />}
    </Hero>
  );
}
