import { useEffect, useRef } from "react";

export default function SpotlightGlow() {
  const glowRef = useRef(null);

  useEffect(() => {
    const el = glowRef.current;
    if (!el) return;

    const handleMove = (e) => {
      el.style.setProperty("--x", `${e.clientX}px`);
      el.style.setProperty("--y", `${e.clientY}px`);
      el.style.opacity = "1";
    };

    const handleLeave = () => {
      el.style.opacity = "0";
    };

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseleave", handleLeave);

    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseleave", handleLeave);
    };
  }, []);

  return <div className="spotlight-glow" ref={glowRef} aria-hidden="true"></div>;
}