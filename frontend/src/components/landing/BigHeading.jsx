const NAVBAR_HEIGHT = 72;
const PIN_GAP = 8;
const START_TOP_VH = 32;
const START_SCALE = 1;
const END_SCALE = 0.33;

export default function BigHeading({ progress }) {
  const scale = START_SCALE - progress * (START_SCALE - END_SCALE);
  const topValue = `calc(${START_TOP_VH - progress * START_TOP_VH}svh + ${
    (NAVBAR_HEIGHT + PIN_GAP) * progress
  }px - var(--hero-nav-height))`;

  return (
    <h1
      className="pin-heading"
      style={{
        top: topValue,
        transform: `translateX(-50%) scale(${scale})`,
      }}
    >
      Understand any video<br />with AI, <span className="shimmer-text">instantly</span>.
      <span
        className="scroll-cue"
        aria-hidden="true"
        style={{ opacity: Math.max(0, 1 - progress * 8) }}
      >
        &#8744;
      </span>
    </h1>
  );
}
