import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The eyebrow, headline and lede that open every section.
 *
 * One component for six sections is the difference between a page that has a rhythm and
 * a page that has six slightly different rhythms. The heading carries an `id` because
 * each section is labelled by its own headline (`aria-labelledby`), which is what makes
 * a landmarks list useful to somebody navigating by headings.
 */
export function SectionHeading({
  id,
  eyebrow,
  title,
  lede,
  align = "left",
  className,
}: {
  id: string;
  eyebrow: string;
  title: ReactNode;
  lede?: ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div className={cn("max-w-3xl", align === "center" && "mx-auto text-center", className)}>
      <p className="font-mono text-[0.7rem] tracking-[0.22em] text-signal-soft uppercase">
        {eyebrow}
      </p>

      <h2
        id={id}
        className="mt-4 font-display text-3xl leading-[1.06] font-semibold tracking-[-0.02em] text-balance sm:text-4xl lg:text-[2.6rem]"
      >
        {title}
      </h2>

      {lede ? (
        <p className="mt-5 text-base/relaxed text-pretty text-muted-foreground sm:text-lg/relaxed">
          {lede}
        </p>
      ) : null}
    </div>
  );
}
