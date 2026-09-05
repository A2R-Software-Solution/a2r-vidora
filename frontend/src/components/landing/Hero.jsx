export default function Hero({ children, compact }) {
  return (
    <section className={compact ? "hero hero-compact" : "hero"}>
      {!compact && <div className="hero-blob" aria-hidden="true"></div>}
      {!compact && (
        <div className="hero-tagline" aria-hidden="true">
          Turn video<br />into <span>knowledge</span>
        </div>
      )}
      {!compact && <div className="badge">AI-powered video intelligence</div>}
      <h1>Explore video<br />with <span>AI</span>.</h1>
      <p className="sub">
        Paste a YouTube link to ask questions, explore transcript excerpts,
        and generate a summary. Verify important details in the original video.
      </p>
      {children}
    </section>
  );
}