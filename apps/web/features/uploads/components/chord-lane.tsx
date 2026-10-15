import type { Segment } from "@myband/shared";

import { clock, isRest, labelOf, type ChordView } from "../chord-view";

/** How many time labels the axis carries, including both ends. */
const TICKS = 5;

/**
 * The whole timeline as one bar, drawn to scale.
 *
 * This is the one thing on the page that a wide display is genuinely better at: a song is
 * a duration, and a duration is a length. Each stretch is placed at its real start and
 * given its real width, so a four-bar chord looks four times as wide as a one-bar chord
 * and the song's shape - where it sits on a chord, where it moves, where it stops - is
 * legible at a glance rather than after reading 170 timings.
 *
 * **Rests are drawn as absence.** A stretch with no chord in it renders nothing at all, so
 * the gap in the bar is the measure of the silence. Drawing a rest as a grey block would
 * be drawing something where the recording had nothing.
 *
 * The whole element is `aria-hidden`, and that is not laziness: the ordered list beneath it
 * is a complete and accessible reading of exactly the same segments, including the timings
 * and the confidence the bar cannot show. The bar is the picture of that list, so it never
 * has to be the way the list is reached.
 *
 * Labels appear only where they fit. At 170 segments a stretch is a few pixels wide and a
 * chord name would be a smear, so the blocks carry their detail in a `title` for a mouse
 * and the list carries it for everybody else. On a six-chord reading the same code labels
 * every block, which is the same figure at two different scales - and the axis under it is
 * always there to say what the width means.
 */
export function ChordLane({
  segments,
  view,
  durationMs,
}: {
  segments: Segment[];
  view: ChordView;
  durationMs: number | null;
}) {
  const [first] = segments;
  const last = segments.at(-1);

  // An empty timeline has no ends to draw from, and `noUncheckedIndexedAccess` means the
  // ends have to be narrowed rather than asserted - which is the same guard.
  if (!first || !last) {
    return null;
  }

  // The span the bar draws: from the first stretch to the end of the last one. The
  // recording's own length is used when the API reported one, because a timeline that
  // stops where the chords stop would overstate the chords' share of the song.
  const from = first.start_ms;
  const to = Math.max(last.end_ms, durationMs ?? 0);

  if (to <= from) {
    return null;
  }

  const spans = segments
    .map((segment) => ({
      segment,
      left: ((segment.start_ms - from) / (to - from)) * 100,
      width: ((segment.end_ms - segment.start_ms) / (to - from)) * 100,
    }))
    .filter((span) => span.width > 0);

  const ticks = Array.from(
    { length: TICKS },
    (_, index) => from + ((to - from) * index) / (TICKS - 1),
  );

  return (
    <div aria-hidden className="overflow-x-auto">
      <div className="min-w-[34rem]">
        <div className="relative h-16 w-full overflow-hidden rounded-xl border border-white/[0.07] bg-black/25">
          {spans.map(({ segment, left, width }, index) => {
            if (isRest(segment)) {
              return null;
            }

            const label = labelOf(segment, view);

            return (
              <span
                key={`${index}-${segment.start_ms}`}
                title={`${clock(segment.start_ms)} · ${label} · ${Math.round(segment.confidence * 100)}%`}
                style={{ left: `${left}%`, width: `${width}%` }}
                // The inset hairline on the right edge is what separates two adjacent
                // chords without spending any of a few pixels' width on a border.
                className="absolute inset-y-1 flex items-center justify-center overflow-hidden rounded-sm bg-gradient-to-b from-signal-soft/90 to-signal-strong/80 shadow-[inset_-1px_0_0_oklch(0_0_0/0.45)]"
              >
                {width >= 8 ? (
                  <span className="truncate px-1 font-mono text-[0.6rem] text-white/90">
                    {label}
                  </span>
                ) : null}
              </span>
            );
          })}
        </div>

        <div className="mt-1.5 flex justify-between font-mono text-[0.6rem] text-muted-foreground tabular-nums">
          {ticks.map((at) => (
            <span key={at}>{clock(at)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
