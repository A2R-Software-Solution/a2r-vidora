import BigHeading from "./BigHeading";
import { useScrollPin } from "../../hooks/useScrollPin";
import { useRevealOnScroll } from "../../hooks/useRevealOnScroll";

const START_TOP_VH = 100; // off-screen (just below first viewport) at scroll = 0
const END_TOP_PX = 190; // final position: just below the pinned heading

export default function Hero({ children, compact }) {
  const progress = useScrollPin(380);
  const [contentRef, contentInView] = useRevealOnScroll(0.15);

  if (compact) {
    return (
      <section className="hero hero-compact">
        <h1 className="reveal-up delay-1">
          Understand any video<br />with AI, <span className="shimmer-text">instantly</span>.
        </h1>
        <p className="sub reveal-up delay-2">
          Paste a YouTube video and ask questions, find exact moments,
          get summaries, or turn long-form videos into ready-to-use Shorts.
        </p>
        {children}
      </section>
    );
  }

  const revealClass = contentInView ? "reveal-on-scroll in-view" : "reveal-on-scroll";
  const topValue = `calc(${START_TOP_VH - progress * START_TOP_VH}vh + ${
    END_TOP_PX * progress
  }px)`;

  return (
    <>
      <BigHeading progress={progress} />

      {/* These stay OUTSIDE hero-lower so they remain fixed to the viewport,
          independent of hero-lower's own transform/position */}
      <div className="hero-blob" aria-hidden="true"></div>
      <div className="hero-tagline hero-tagline-right" aria-hidden="true">
        Turn any video<br />into <span>knowledge</span>
      </div>
      <div className="hero-tagline hero-tagline-left" aria-hidden="true">
        From hours<br />of watching...
        <svg className="tagline-arrow draw-arrow" viewBox="0 0 60 50" fill="none">
          <path d="M5 5 Q 30 10, 40 40" stroke="#ff6b35" strokeWidth="2" strokeLinecap="round"/>
          <path d="M32 34 L40 40 L34 28" stroke="#ff6b35" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      <section
        className="hero hero-lower"
        ref={contentRef}
        style={{ top: topValue }}
      >
        <div className={`badge ${revealClass} delay-0`}>AI-powered video intelligence</div>
        <p className={`sub ${revealClass} delay-1`}>
          Paste a YouTube video and ask questions, find exact moments,
          get summaries, or turn long-form videos into ready-to-use Shorts.
        </p>
        <div className={`${revealClass} delay-2`}>
          {children}
        </div>
      </section>
    </>
  );
}