import { useEffect, useRef, useState } from "react";

/**
 * Returns a ref to attach to an element and a boolean that becomes
 * true once the element enters the viewport. Used to trigger
 * fade-slide-up reveal animations as sections scroll into view.
 */
export function useRevealOnScroll(threshold = 0.2) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  return [ref, inView];
}