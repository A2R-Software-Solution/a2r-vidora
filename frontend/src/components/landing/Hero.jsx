export default function Hero({ children, compact }) {
  return (
    <section className={compact ? "hero hero-compact" : "hero"}>
      {!compact && <div className="hero-blob" aria-hidden="true"></div>}
      {!compact && (
        <div className="hero-tagline hero-tagline-right" aria-hidden="true">
          Turn any video<br />into <span>knowledge</span>
        </div>
      )}
      {!compact && (
        <div className="hero-tagline hero-tagline-left" aria-hidden="true">
          From hours<br />of watching...
          <svg className="tagline-arrow" viewBox="0 0 60 50" fill="none">
            <path d="M5 5 Q 30 10, 40 40" stroke="#ff6b35" strokeWidth="2" strokeLinecap="round"/>
            <path d="M32 34 L40 40 L34 28" stroke="#ff6b35" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      )}
      {!compact && <div className="badge">AI-powered video intelligence</div>}
      <h1>Understand any video<br />with AI, <span>instantly</span>.</h1>
      <p className="sub">
        Paste a YouTube video and ask questions, find exact moments,
        get summaries, or turn long-form videos into ready-to-use Shorts.
      </p>
      {children}
    </section>
  );
}