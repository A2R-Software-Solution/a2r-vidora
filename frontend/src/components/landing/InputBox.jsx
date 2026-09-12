import { useEffect, useState, useRef } from "react";
import { isYouTubeVideoUrl, YOUTUBE_LINK_MESSAGE } from "../../utils/videoInput";

function AnalysisStatus({ restoring }) {
  const [takingLonger, setTakingLonger] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setTakingLonger(true), 60_000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="analysis-status" role="status" aria-live="polite" aria-atomic="true">
      {restoring ? (
        <strong>Retrieving your previous analysis…</strong>
      ) : takingLonger ? (
        <strong>Still working on your video. Thanks for your patience!</strong>
      ) : (
        <>
          <strong>Hang tight! We’re getting your video ready.</strong>
          <span>Our system may need a moment to warm up. This can take about a minute.</span>
        </>
      )}
    </div>
  );
}

export default function InputBox({ onAnalyze, loading, restoring = false, error, onClearError }) {
  const [url, setUrl] = useState("");
  const [validationError, setValidationError] = useState(null);
  const inputRef = useRef(null);
  const visibleError = validationError || error;
  const btnRef = useRef(null);

  const handleAnalyze = () => {
    const trimmed = url.trim();
    if (!isYouTubeVideoUrl(trimmed)) {
      setValidationError(YOUTUBE_LINK_MESSAGE);
      onClearError?.();
      inputRef.current?.focus();
      return;
    }
    setValidationError(null);
    onAnalyze(trimmed);
  };

  const handleBtnMove = (e) => {
    const btn = btnRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    btn.style.transform = `translate(${x * 0.25}px, ${y * 0.4}px)`;
  };

  const handleBtnLeave = () => {
    const btn = btnRef.current;
    if (!btn) return;
    btn.style.transform = "translate(0, 0)";
  };

  return (
    <>
      <div className="input-wrap reveal-up delay-3">
        <span className="input-icon" aria-hidden="true">🔍</span>
        <input
          ref={inputRef}
          aria-label="YouTube video link"
          aria-invalid={Boolean(validationError)}
          aria-describedby={visibleError ? "analysis-input-error" : undefined}
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setValidationError(null);
            onClearError?.();
          }}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={loading}
        />
        <button
          ref={btnRef}
          className="analyze magnetic-btn"
          onClick={handleAnalyze}
          onMouseMove={handleBtnMove}
          onMouseLeave={handleBtnLeave}
          disabled={loading}
          aria-label={loading ? (restoring ? "Retrieving previous analysis" : "Analyzing video") : undefined}
        >
          {loading ? (
            <span className="btn-loading" aria-hidden="true">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </span>
          ) : (
            "Analyze Video →"
          )}
        </button>
      </div>
      {loading && <AnalysisStatus restoring={restoring} />}
      {visibleError && <div id="analysis-input-error" className="analysis-status analysis-error" role="alert">{visibleError}</div>}
      <div className="providers reveal-up delay-4">
        <span><span className="provider-icon yt">▶</span> YouTube</span>
        <span><span className="provider-icon vimeo">V</span> Vimeo</span>
        <span><span className="provider-icon drive">▲</span> Google Drive</span>
        <span>⋯ And more</span>
      </div>
      <div className="hint reveal-up delay-4">
        Free beta supports YouTube videos up to 35 minutes.
      </div>
    </>
  );
}
