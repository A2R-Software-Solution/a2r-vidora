import { useState } from "react";

export default function InputBox({ onAnalyze, loading }) {
  const [url, setUrl] = useState("");

  const handleAnalyze = () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    onAnalyze(trimmed);
  };

  return (
    <>
      <div className="input-wrap">
        <span className="input-icon" aria-hidden="true">🔍</span>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={loading}
        />
        <button className="analyze" onClick={handleAnalyze} disabled={loading}>
          {loading ? "Analyzing..." : "Analyze Video →"}
        </button>
      </div>
      <div className="providers">
        <span>▶ YouTube</span>
        <span>🎬 Vimeo</span>
        <span>📁 Google Drive</span>
        <span>⋯ And more</span>
      </div>
      <div className="hint">Just paste the link. No login. No hassle.</div>
    </>
  );
}