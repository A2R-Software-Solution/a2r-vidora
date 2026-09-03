export default function Hero({ children }) {
  return (
    <section className="hero">
      <div className="badge">AI-powered video intelligence</div>
      <h1>Understand any video.<br /><span>Instantly.</span></h1>
      <p className="sub">
        Paste a YouTube video and ask questions, find exact moments,
        get summaries, or turn long-form videos into ready-to-use Shorts.
      </p>
      {children}
    </section>
  );
}