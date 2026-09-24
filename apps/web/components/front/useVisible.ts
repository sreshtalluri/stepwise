"use client";

import { useEffect, useState, type RefObject } from "react";

/** True while at least `threshold` of the element is on screen. */
export function useVisible(ref: RefObject<Element | null>, threshold = 0.2): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, threshold]);
  return visible;
}
