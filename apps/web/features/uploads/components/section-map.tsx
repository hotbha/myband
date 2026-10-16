import type { Section, Sections } from "@myband/shared";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { MicroLabel } from "@/features/design-system/components/eyebrow";

import { clock } from "../chord-view";

/** How many time labels the axis carries, including both ends. */
const TICKS = 5;

/**
 * A song's sections, drawn as the shape they are.
 *
 * The same three passes the chord band makes, at the scale a section lives at: the whole song as one
 * scale drawing, the form as an aside, and every section in order underneath - which is also the
 * accessible reading of the drawing above it.
 *
 * **The letters are the reading.** `A` beside `A` means the same music twice, and that is the whole
 * of what this detector claims; the aside says so in as many words, because a reader who took `A`
 * for "verse" would be reading a claim nobody made. Naming a section changes when something reads
 * the lyrics, and not before.
 *
 * Sections are drawn as touching blocks, unlike the chord lane's rests: sections cover the
 * recording by construction, so a gap in this bar would be a gap in the arithmetic rather than in
 * the song.
 *
 * `clock` is borrowed from `chord-view.ts` rather than copied: a timestamp is a timestamp, and the
 * two screens have to format one the same way.
 */
export function SectionMap({
  sections,
  durationMs,
}: {
  sections: Sections;
  durationMs: number | null;
}) {
  const list = sections.sections;
  const first = list.at(0);
  const last = list.at(-1);

  // Written out rather than interpolated in the middle of the sentence: a JSX text run broken
  // across lines around an expression is a whitespace question nobody should have to think about,
  // and this one has a hyphen on the far side of it.
  const pool = `${Math.round(sections.hop_ms / 1000)}-second`;

  if (!first || !last) {
    return (
      <EmptyState>
        This recording had nothing to tell apart. Every stretch of it sounds like every other, so
        there are no sections to name - the tempo, key, chords and MIDI were still measured.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-xs/relaxed text-muted-foreground">
        Read from the recording by {sections.detector}, in {pool} blocks. A letter is a stretch of
        music; the same letter is the same music heard again.
      </p>

      <Lane list={list} durationMs={durationMs} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:items-start">
        <ol className="divide-y divide-white/[0.07] overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.02]">
          {list.map((section, index) => (
            <Row key={`${index}-${section.start_ms}`} section={section} />
          ))}
        </ol>

        <Form sections={sections} />
      </div>
    </div>
  );
}

/**
 * The whole song as one bar, each section placed at its real start and given its real width.
 *
 * The first kind of music is the accented one and everything else is neutral, which is the same rule
 * the chord band's card follows: a strip where every block is highlighted is a strip that ranks
 * nothing. The accent marks where the song begins, and the letters carry the rest.
 *
 * `aria-hidden`, because the ordered list beneath is a complete reading of the same sections -
 * including the timings the bar cannot show.
 */
function Lane({ list, durationMs }: { list: Section[]; durationMs: number | null }) {
  const first = list.at(0);
  const last = list.at(-1);

  if (!first || !last) {
    return null;
  }

  // The span the bar draws: the whole recording where the API reported one, so a list that stops
  // short of the end shows as stopping short.
  const from = first.start_ms;
  const to = Math.max(last.end_ms, durationMs ?? 0);

  if (to <= from) {
    return null;
  }

  const ticks = Array.from(
    { length: TICKS },
    (_, index) => from + ((to - from) * index) / (TICKS - 1),
  );

  return (
    <div aria-hidden className="overflow-x-auto">
      <div className="min-w-[34rem]">
        <div className="relative h-14 w-full overflow-hidden rounded-xl border border-white/[0.07] bg-black/25">
          {list.map((section, index) => {
            const width = ((section.end_ms - section.start_ms) / (to - from)) * 100;

            return (
              <span
                key={`${index}-${section.start_ms}`}
                title={`${section.label} · ${clock(section.start_ms)} - ${clock(section.end_ms)}`}
                style={{
                  left: `${((section.start_ms - from) / (to - from)) * 100}%`,
                  width: `${width}%`,
                }}
                className={
                  section.label === first.label
                    ? "absolute inset-y-1 flex items-center justify-center overflow-hidden rounded-sm bg-gradient-to-b from-signal-soft/90 to-signal-strong/80 shadow-[inset_-1px_0_0_oklch(0_0_0/0.45)]"
                    : "absolute inset-y-1 flex items-center justify-center overflow-hidden rounded-sm bg-white/[0.12] shadow-[inset_-1px_0_0_oklch(0_0_0/0.45)]"
                }
              >
                {width >= 4 ? (
                  <span className="truncate px-1 font-mono text-[0.6rem] text-white/90">
                    {section.label}
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

/**
 * One section, and where it hands over.
 *
 * The end is shown rather than a duration on purpose: a section ends exactly where the next begins,
 * so the two timestamps say both things and neither has to be subtracted to read the row.
 */
function Row({ section }: { section: Section }) {
  return (
    <li className="flex items-center gap-3 p-3">
      <time className="w-12 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
        {clock(section.start_ms)}
      </time>

      <span className="inline-flex min-w-16 justify-center rounded-lg border border-white/10 bg-white/[0.05] px-2 py-0.5 font-mono text-sm font-medium text-foreground">
        {section.label}
      </span>

      <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
        to {clock(section.end_ms)}
      </span>
    </li>
  );
}

/**
 * The form, and the one sentence that keeps it honest.
 *
 * The form is read from the digest the worker wrote rather than rebuilt from the list beside it -
 * two definitions of a form is how a row and a screen come to disagree about one song - so a list
 * written before the digest held one shows no form at all, which is the honest fallback.
 */
function Form({ sections }: { sections: Sections }) {
  const form = formOf(sections);
  const count = countOf(sections);

  if (form === null) {
    return null;
  }

  const kinds = distinct(sections);

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <MicroLabel>Form</MicroLabel>

      <p className="mt-3 font-mono text-lg tracking-[0.2em] break-words">{form}</p>

      {count === null ? null : (
        <p className="mt-3 text-xs/relaxed text-muted-foreground">
          {count} {count === 1 ? "section" : "sections"}, {kinds}{" "}
          {kinds === 1 ? "of them one piece of music" : "different pieces of music"}.
        </p>
      )}

      <p className="mt-3 text-xs/relaxed text-muted-foreground">
        A letter, not a name. Telling a chorus from a verse takes the lyrics, so this says the one
        thing it can hear: which stretches are the same music.
      </p>
    </div>
  );
}

/** The form the worker wrote, or `null` when the digest does not hold one. */
function formOf(sections: Sections): string | null {
  const form = sections.summary["form"];

  return typeof form === "string" && form.length > 0 ? form : null;
}

/** How many sections the digest says there are, or `null` when it does not say. */
function countOf(sections: Sections): number | null {
  const count = sections.summary["sections"];

  return typeof count === "number" ? count : null;
}

/** How many distinct pieces of music the recording is made of, read off the list itself. */
function distinct(sections: Sections): number {
  return new Set(sections.sections.map((section) => section.label)).size;
}
