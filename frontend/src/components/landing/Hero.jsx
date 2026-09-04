export default function Hero({ children, compact }) {
  return (
    <section className={compact ? "hero hero-compact" : "hero"}>
      {!compact && <div className="hero-blob" aria-hidden="true"></div>}
      {!compact && (
        <div className="hero-tagline" aria-hidden="true">
          Turn any video<br />into <span>knowledge</span>
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