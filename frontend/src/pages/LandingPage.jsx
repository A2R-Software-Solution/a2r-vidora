import Hero from "../components/landing/Hero";
import InputBox from "../components/landing/InputBox";
import Features from "../components/landing/Features";
import { useVideoAnalyze } from "../hooks/useVideoAnalyze";

export default function LandingPage({ onAnalyzed, compact }) {
  const { submitVideo, loading, error } = useVideoAnalyze();

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
      {error && <div className="error-text" role="alert">{error}</div>}
      {!compact && <Features />}
    </Hero>
  );
}