"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

/**
 * A section that arrives as you scroll to it.
 *
 * One motion primitive for the whole page rather than a `whileInView` on every heading,
 * card and paragraph: the reveal is the page's rhythm, and it should be impossible for
 * one section to end up with a different one.
 *
 * `viewport` is `once`, so a section that has been read does not animate a second time
 * when somebody scrolls back up to check a number - which is what people do on this page.
 * The easing is a long decelerating curve; the page should feel like it settles rather
 * than like it snaps.
 *
 * Reduced motion is not handled here. It is handled once, in `MotionConfig` at the shell,
 * which is both cheaper and correct: `prefers-reduced-motion` cannot be read during a
 * server render, so branching on it here would mean the server and the client disagree
 * about the first paint.
 *
 * `data-reveal` is what the shell's `<noscript>` stylesheet hooks into: with JavaScript
 * off, these wrapper styles would leave every section invisible forever.
 */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      data-reveal=""
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
