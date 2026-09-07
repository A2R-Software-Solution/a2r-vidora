import { useEffect, useState } from "react";

/**
 * Tracks scroll progress from 0 to 1 over the given pixel range.
 * Used to drive the big heading's shrink + pin transition as the
 * user scrolls from the top of the page.
 */
export function useScrollPin(range = 400) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const y = window.scrollY;
      const value = Math.min(1, Math.max(0, y / range));
      setProgress(value);
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [range]);

  return progress;
}