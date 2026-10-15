import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

import { Eyebrow } from "./eyebrow";

/**
 * A region of a screen: the level-1 surface of the design system.
 *
 * This is the landing page's analyser panel, made reusable. It is the whole recipe -
 * a glass fill, a 24px radius, a hairline edge and the signal gradient along the top
 * edge - and it is deliberately one component rather than a class string copied into
 * every screen, because "the same surface everywhere" is the point of this change.
 *
 * A `section` rather than a `div`, and props are spread so a caller can name it with
 * `aria-labelledby`. An unnamed `section` is not a landmark, so a panel used purely as
 * a layout wrapper costs nothing.
 *
 * `overflow-hidden` is what lets the hairline be absolutely positioned without a
 * caller having to remember it, and `backdrop-blur-xl` belongs here rather than on the
 * tiles inside: blurring forty rows is how a list becomes slow, and a tile sitting on
 * an already-blurred panel gains nothing from blurring again.
 */
export function Panel({ className, children, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-3xl border border-white/[0.07] bg-white/[0.025] p-5 backdrop-blur-xl sm:p-6",
        className,
      )}
      {...props}
    >
      <div
        aria-hidden
        className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-signal/60 to-transparent"
      />

      {children}
    </section>
  );
}

/**
 * A panel's heading: what it is, and what belongs on the right of it.
 *
 * `right` is one slot rather than two on purpose. A panel that wants both a hint and a
 * control has a layout problem, not a component problem - and a slot that accepts either
 * keeps the heading a flex row with two children, which is why every panel in the
 * product reads at the same rhythm.
 *
 * The title is an `h2` and carries the panel's `id`, so a screen can point a section's
 * `aria-labelledby` at it without a second element.
 */
export function PanelHeader({
  id,
  eyebrow,
  title,
  right,
  className,
}: {
  id?: string;
  eyebrow: string;
  title?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0">
        <Eyebrow>{eyebrow}</Eyebrow>

        {title ? (
          <h2 id={id} className="mt-1.5 font-display text-lg font-medium tracking-tight">
            {title}
          </h2>
        ) : null}
      </div>

      {right ? <div className="shrink-0">{right}</div> : null}
    </header>
  );
}
