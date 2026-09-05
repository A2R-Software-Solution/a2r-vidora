import { useState } from "react";
import ProcessingNotice from "../governance/ProcessingNotice";

export default function InputBox({ onAnalyze, loading }) {
  const [url, setUrl] = useState("");

  const handleAnalyze = (event) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || loading) return;
    onAnalyze(trimmed);
  };

  return (
    <>
      <ProcessingNotice />
      <form className="input-wrap" onSubmit={handleAnalyze} aria-describedby="processing-notice">
        <span className="input-icon" aria-hidden="true">🔍</span>
        <input type="url" aria-label="YouTube video URL" required maxLength={500}
          value={url} onChange={(event) => setUrl(event.target.value)}
          placeholder="https://www.youtube.com/watch?v=..." disabled={loading} />
        <button className="analyze" type="submit" disabled={loading || !url.trim()}>
          {loading ? "Analyzing..." : "Analyze Video →"}
        </button>
      </form>
      <div className="hint" role="status">{loading ? "Processing video. This may take a few minutes." : "YouTube videos supported"}</div>
    </>
  );
}
