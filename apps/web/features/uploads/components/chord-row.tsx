import { NO_CHORD, type Segment } from "@myband/shared";

import { cn } from "@/lib/utils";

import { clock, held, labelOf, type ChordView } from "../chord-view";

/** Every row: a time, a label, how long it is held, and the space between them. */
const ROW = "flex items-center gap-3 p-3";

/**
 * One stretch of the song.
 *
 * The row is a `<details>` exactly when the reading on screen is not the one the detector
 * produced and the two disagree about this chord - the only case where anything is behind
 * the label. Nothing is disclosed in the detected view: there, every row already says what
 * was heard.
 *
 * It is a native `<details>` rather than a stateful disclosure, which is why there is no
 * state for it here: a keyboard and a screen reader get it right for free.
 */
export function ChordRow({ segment, view }: { segment: Segment; view: ChordView }) {
  const silent = segment.chord === NO_CHORD;
  const label = labelOf(segment, view);
  const simplified = !silent && label !== segment.chord;

  if (!simplified) {
    return (
      <li className={ROW}>
        <RowLine segment={segment} label={label} silent={silent} />
      </li>
    );
  }

  return (
    <li>
      <details className="group">
        <summary className={cn(ROW, "cursor-pointer list-none [&::-webkit-details-marker]:hidden")}>
          <RowLine segment={segment} label={label} silent={silent} />
          <span className="sr-only">, simplified</span>
          <span
            aria-hidden
            className="shrink-0 text-[10px] text-muted-foreground transition-transform group-open:rotate-180"
          >
            ▾
          </span>
        </summary>
        <p className="px-3 pb-3 text-xs text-muted-foreground">
          Detected as <span className="font-mono">{segment.chord}</span>.
        </p>
      </details>
    </li>
  );
}

/** What every row shows, whether or not it is also a disclosure. */
function RowLine({ segment, label, silent }: { segment: Segment; label: string; silent: boolean }) {
  return (
    <>
      <time className="w-12 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
        {clock(segment.start_ms)}
      </time>
      <ChordLabel label={label} silent={silent} />
      <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
        {held(segment.end_ms - segment.start_ms)}
      </span>
    </>
  );
}

/** The chord itself, with a rest drawn as the absence of one rather than as a label. */
function ChordLabel({ label, silent }: { label: string; silent: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-16 justify-center rounded-lg border px-2 py-0.5 font-mono text-sm font-medium",
        silent
          ? "border-dashed border-border text-muted-foreground"
          : "border-white/10 bg-white/[0.05] text-foreground",
      )}
    >
      {silent ? "rest" : label}
    </span>
  );
}
