import { useEffect, useState } from "react";

/**
 * Tracks scroll progress from 0 to 1 over the given pixel range. Updates are
 * batched with requestAnimationFrame so React does not re-render for every
 * browser scroll event.
 */
export function useScrollPin(range = 400) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frameId = null;

    const handleScroll = () => {
      if (frameId !== null) return;

      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        const nextProgress = Math.min(1, Math.max(0, window.scrollY / range));
        setProgress((currentProgress) =>
          currentProgress === nextProgress ? currentProgress : nextProgress
        );
      });
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      window.removeEventListener("scroll", handleScroll);
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, [range]);

  return progress;
}
