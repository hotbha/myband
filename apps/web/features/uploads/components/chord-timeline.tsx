"use client";

import { useState } from "react";

import { type Chords, type Segment } from "@myband/shared";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { EmptyState } from "@/features/design-system/components/empty-state";
import { MicroLabel } from "@/features/design-system/components/eyebrow";

import { CHORD_VIEWS, cardOf, isRest, meanConfidence, type ChordView } from "../chord-view";
import { ChordLane } from "./chord-lane";
import { ChordRow } from "./chord-row";

/**
 * A song's chords, in order, as the one thing a reader wants from them: what is played when.
 *
 * **Two readings of the same timeline**, and the toggle between them is what this is
 * about - see `chord-view.ts` for what each one means. The simple reading is the default
 * because the alternative is a wall of `Fmaj7`, `Am7` and `C/E` when four chords are being
 * played; the detected labels are one tap away, and a row whose two readings differ says so
 * on the row itself.
 *
 * The band is read in three passes, widest first:
 *
 * 1. **the lane** - the whole song as one scale drawing, which is the only part of this
 *    that a wide screen makes materially better;
 * 2. **the ranked progression and the confidence**, as an aside that sticks while the list
 *    scrolls past it, because "which chords does this song live on" is the question
 *    somebody has while reading bars 40 to 90;
 * 3. **every stretch, in order**, which is the complete record and the accessible reading
 *    of the lane above it.
 *
 * Confidence is not disclosed per row. A detector that was between 57% and 86% sure of all
 * 169 segments of a song was not making 169 different judgements, and 169 near-identical
 * meters would say nothing about the one thing worth knowing - so it is one sentence, and
 * the number that really is per-view, how much of the recording the chords account for, is
 * the one that gets a bar.
 *
 * A client component, unlike the rest of the page: the timeline arrived with the request,
 * so comparing the two readings is a state change rather than a refetch.
 */
export function ChordTimeline({
  chords,
  durationMs,
}: {
  chords: Chords;
  durationMs: number | null;
}) {
  const [view, setView] = useState<ChordView>("simple");
  const named = chords.segments.filter((segment) => !isRest(segment));
  const empty = chords.segments.length === 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs/relaxed text-muted-foreground">
          Read from the recording by {chords.detector}, bar by bar
          {chords.key ? ` in ${chords.key}` : ""}. Times are when each chord starts.
        </p>

        {empty ? null : <ViewToggle view={view} onChange={setView} />}
      </div>

      {empty ? (
        <EmptyState>
          This recording has no chords in it at all. That is usually a percussion or spoken-word
          track, and it is not an error - the tempo, key and MIDI were still measured.
        </EmptyState>
      ) : (
        <>
          <ChordLane segments={chords.segments} view={view} durationMs={durationMs} />

          <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:items-start">
            <ol className="divide-y divide-white/[0.07] overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.02]">
              {chords.segments.map((segment) => (
                <ChordRow
                  key={`${segment.start_ms}-${segment.chord}`}
                  segment={segment}
                  view={view}
                />
              ))}
            </ol>

            <aside className="space-y-4 lg:sticky lg:top-24">
              <Progression chords={chords} view={view} />
              <Confidence chords={chords} named={named} />
              <Rests count={chords.segments.length - named.length} />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The two readings, side by side.
 *
 * Buttons rather than a control of its own, and this app's own `Button` rather than a new
 * primitive: two states with one of them on is what `aria-pressed` describes.
 */
function ViewToggle({ view, onChange }: { view: ChordView; onChange: (view: ChordView) => void }) {
  return (
    <div role="group" aria-label="Chord labels" className="inline-flex items-center gap-1">
      {CHORD_VIEWS.map((option) => (
        <Button
          key={option.view}
          type="button"
          size="xs"
          variant={view === option.view ? "secondary" : "ghost"}
          aria-pressed={view === option.view}
          title={option.hint}
          onClick={() => onChange(option.view)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

/**
 * The chords this reading says the song is made of, and how much of the recording they
 * account for.
 *
 * Both come from the API, so nothing is ranked twice here - and a timeline stored before
 * the digest held a progression has no ranking, which is simply no card. The coverage is
 * the number worth a bar: it is a share of a whole, and the difference between a card
 * accounting for 92% of a recording and one accounting for 59% is the difference between a
 * description of a song and a list of its landmarks.
 *
 * The first chip carries the accent and the rest do not, because the ranking is shown once.
 * A strip where every chord is highlighted is a strip that ranks nothing.
 */
function Progression({ chords, view }: { chords: Chords; view: ChordView }) {
  const card = cardOf(chords, view);

  if (card.chords.length === 0) {
    return null;
  }

  const percent = Math.round(card.coverage * 100);

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <MicroLabel>Made of</MicroLabel>

      <ul className="mt-3 flex flex-wrap gap-2">
        {card.chords.map((chord, index) => (
          <li
            key={chord}
            className={
              index === 0
                ? "rounded-lg border border-signal/25 bg-signal/[0.07] px-2.5 py-1 font-mono text-sm"
                : "rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1 font-mono text-sm"
            }
          >
            {chord}
          </li>
        ))}
      </ul>

      <div className="mt-4 space-y-2">
        <Progress
          value={percent}
          className="h-1.5"
          aria-label={`These chords account for ${percent} percent of the recording`}
        />
        <p className="font-mono text-xs text-muted-foreground tabular-nums">
          {percent}% of the recording
        </p>
      </div>
    </div>
  );
}

/**
 * How sure the detector was, in one sentence rather than a meter on every row.
 *
 * The level is the digest's own confidence and is deliberately not worked out again here,
 * because a second mean would be a second definition of it. The spread is read off the
 * rows, and is the part a mean cannot give: whether every bar was equally unsure or one bar
 * was lost. A narrow band is a detector guessing throughout; a wide one is a detector that
 * knows which bars it got.
 */
function Confidence({ chords, named }: { chords: Chords; named: Segment[] }) {
  const mean = meanConfidence(chords);

  if (named.length === 0 || mean === null) {
    return null;
  }

  const percents = named.map((segment) => Math.round(segment.confidence * 100));
  const lowest = Math.min(...percents);
  const highest = Math.max(...percents);
  const spread = lowest === highest ? `${lowest}%` : `${lowest}% to ${highest}%`;

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <MicroLabel>Confidence</MicroLabel>

      <p className="mt-2 font-mono text-2xl leading-none tabular-nums">
        {Math.round(mean * 100)}
        <span className="ml-0.5 text-sm text-muted-foreground">%</span>
      </p>

      <p className="mt-2 text-xs/relaxed text-muted-foreground">
        Mean, and {spread} on every chord it named. The bars it got wrong are the ones worth a
        second listen.
      </p>
    </div>
  );
}

/** How much of the recording had nothing in it, said the way the lane and the rows draw it. */
function Rests({ count }: { count: number }) {
  if (count === 0) {
    return null;
  }

  return (
    <p className="px-1 text-xs/relaxed text-muted-foreground">
      {count === 1 ? "One stretch" : `${count} stretches`} of this recording had no chord in it -
      the gaps in the bar above, and <span className="font-mono">rest</span> in the list.
    </p>
  );
}
