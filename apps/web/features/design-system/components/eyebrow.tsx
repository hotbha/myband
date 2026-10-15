import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The small mono label above a heading.
 *
 * One of the two type styles the design system sets aside for labels, and the one that
 * carries the accent: a signal-soft eyebrow opens every section on the landing page and
 * every panel in the workspace, which is what makes the two surfaces read as one
 * product. The other style is the micro-label inside a metric, and it stays grey - a
 * panel gets one accent, and this is it.
 *
 * The tracking is wide because the text is uppercase and short. `0.22em` is not a value
 * to tune per call site, so it is not a prop.
 */
export function Eyebrow({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <p
      className={cn(
        "font-mono text-[0.7rem] tracking-[0.22em] text-signal-soft uppercase",
        className,
      )}
    >
      {children}
    </p>
  );
}

/**
 * The micro-label above a metric's value.
 *
 * Deliberately grey where `Eyebrow` is accent: a metric tile is the one place in a panel
 * where a number should be the loudest thing, and a coloured label above it competes
 * with the number it is labelling.
 */
export function MicroLabel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        "font-mono text-[0.6rem] tracking-[0.16em] text-muted-foreground uppercase",
        className,
      )}
    >
      {children}
    </span>
  );
}
