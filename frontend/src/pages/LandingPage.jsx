import Hero from "../components/landing/Hero";
import InputBox from "../components/landing/InputBox";
import Features from "../components/landing/Features";
import { useVideoAnalyze } from "../hooks/useVideoAnalyze";

export default function LandingPage({ onAnalyzed }) {
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
    <Hero>
      <InputBox onAnalyze={handleAnalyze} loading={loading} />
      {error && <div className="error-text">{error}</div>}
      <Features />
    </Hero>
  );
}