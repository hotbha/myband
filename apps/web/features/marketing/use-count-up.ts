"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A measured value that counts up to itself.
 *
 * The analyser panel is the page's one piece of theatre, and a number that arrives
 * already printed reads as an image, while a number that counts up reads as an instrument
 * taking a reading. The easing is cubic-out so it decelerates into the answer instead of
 * stopping dead.
 *
 * Three details are deliberate:
 *
 * * the first render is always `0`, on the server and on the client, so there is nothing
 *   for React to disagree about when it hydrates;
 * * a reader who has asked for reduced motion gets the final value immediately - a
 *   counter cannot be switched off from CSS, so this is one of the few places where the
 *   preference has to be read in JavaScript;
 * * the frame is cancelled on unmount, because a hero that has scrolled away should not
 *   still be scheduling work.
 */
export function useCountUp(
  target: number,
  { duration = 1500, decimals = 0 }: { duration?: number; decimals?: number } = {},
): string {
  const [value, setValue] = useState(0);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced) {
      setValue(target);
      return;
    }

    const started = performance.now();

    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);

      setValue(target * eased);

      if (progress < 1) {
        frame.current = requestAnimationFrame(tick);
      }
    };

    frame.current = requestAnimationFrame(tick);

    return () => {
      if (frame.current !== null) {
        cancelAnimationFrame(frame.current);
      }
    };
  }, [target, duration]);

  return decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
}
