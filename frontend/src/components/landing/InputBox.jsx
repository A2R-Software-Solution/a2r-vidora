import { useState, useRef } from "react";

export default function InputBox({ onAnalyze, loading }) {
  const [url, setUrl] = useState("");
  const btnRef = useRef(null);

  const handleAnalyze = () => {
    const trimmed = url.trim();
    if (!trimmed) return;
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
          value={url}
          onChange={(e) => setUrl(e.target.value)}
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
        >
          {loading ? (
            <span className="btn-loading">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </span>
          ) : (
            "Analyze Video →"
          )}
        </button>
      </div>
      <div className="providers reveal-up delay-4">
        <span><span className="provider-icon yt">▶</span> YouTube</span>
        <span><span className="provider-icon vimeo">V</span> Vimeo</span>
        <span><span className="provider-icon drive">▲</span> Google Drive</span>
        <span>⋯ And more</span>
      </div>
      <div className="hint reveal-up delay-4">Just paste the link. No login. No hassle.</div>
    </>
  );
}