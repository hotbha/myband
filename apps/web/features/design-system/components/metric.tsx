import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { MicroLabel } from "./eyebrow";

/**
 * One measurement: a label, the value, its unit, and the sentence that keeps it honest.
 *
 * Three parts, always. A tile with a bare number is an incomplete tile - `117.45 BPM` is
 * a fact, `tracked, not guessed` is why it can be trusted - and the hint is also where
 * the second reading of a value goes (`C# minor` with `strength 0.824` under it).
 *
 * The value is monospace with `tabular-nums`, because every number this product reports
 * is a measurement and measurements should line up in a column. A metric that is not a
 * measurement - a title, a detector's name - takes `mono={false}` instead of being
 * dressed as one.
 *
 * Renders a `<div>` wrapping a `<dt>`/`<dd>` pair, which is valid inside a `<dl>`: the
 * grid of metrics on a screen is one definition list, and the browser's accessibility
 * tree then reads "Tempo, 117.45 BPM" rather than two unrelated strings.
 */
export function Metric({
  label,
  value,
  unit,
  hint,
  mono = true,
  className,
}: {
  label: string;
  value: string;
  unit?: string;
  hint: string;
  /** `false` for a value that is a name rather than a number. */
  mono?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn("rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5", className)}
    >
      <dt>
        <MicroLabel>{label}</MicroLabel>
      </dt>

      <dd className="mt-1.5 flex items-baseline gap-1">
        <span
          className={cn(
            "min-w-0 truncate text-lg leading-none font-medium",
            mono && "font-mono tabular-nums",
          )}
        >
          {value}
        </span>
        {unit ? (
          <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground">{unit}</span>
        ) : null}
      </dd>

      <dd className="mt-1.5 text-[0.68rem] text-muted-foreground/80">{hint}</dd>
    </div>
  );
}

/**
 * One row of a "how this was measured" list: a label and a value that is not a headline.
 *
 * The metric is for a number worth reading across a room; this is for the provenance
 * details beside it - a detector's name, a hop size in milliseconds, a job id. They are
 * monospace for the same reason and quieter for a different one.
 */
export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/[0.07] py-2 last:border-0">
      <dt className="shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-right font-mono text-xs">{children}</dd>
    </div>
  );
}
