import { useState } from "react";

export default function InputBox({ onAnalyze, loading }) {
  const [url, setUrl] = useState("");

  const handleAnalyze = () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    onAnalyze(trimmed);
  };

  return (
    <div className="input-wrap">
      <input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste a YouTube URL..."
        disabled={loading}
      />
      <button className="analyze" onClick={handleAnalyze} disabled={loading}>
        {loading ? "Analyzing..." : "Analyze video →"}
      </button>
    </div>
  );
}