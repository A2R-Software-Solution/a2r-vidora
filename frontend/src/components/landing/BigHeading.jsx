const NAVBAR_HEIGHT = 72;
const PIN_GAP = 8;
const START_TOP_VH = 32;
const START_SCALE = 1;
const END_SCALE = 0.22;

export default function BigHeading({ progress }) {
  const scale = START_SCALE - progress * (START_SCALE - END_SCALE);
  const topValue = `calc(${START_TOP_VH - progress * START_TOP_VH}vh + ${
    (NAVBAR_HEIGHT + PIN_GAP) * progress
  }px)`;

  return (
    <>
      {/* Fixed-height spacer: does NOT shrink, so document scroll height stays stable */}
      <div className="pin-heading-spacer" />
      <h1
        className="pin-heading"
        style={{
          top: topValue,
          transform: `translateX(-50%) scale(${scale})`,
        }}
      >
        Understand any video<br />with AI, <span className="shimmer-text">instantly</span>.
      </h1>
    </>
  );
}
