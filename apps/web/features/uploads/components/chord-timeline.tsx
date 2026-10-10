"use client";

import { useState } from "react";

import { NO_CHORD, type Chords, type Segment } from "@myband/shared";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/**
 * A song's chords, in order, as the one thing a reader wants from them: what is played when.
 *
 * Two readings of the same timeline, and the toggle between them is what this is about. **Simple**
 * shows each chord as the triad underneath it, which is what someone playing along wants; **as
 * detected** shows the label the detector actually produced, extension and inversion included. The
 * simple reading is the default because the alternative is a wall of `Fmaj7`, `Am7` and `C/E` when
 * four chords are being played - but it is a *reading* and not a correction, so the detected labels
 * are one tap away, and a row whose two readings differ says so on the row itself.
 *
 * That disclosure is a native `<details>`, which is why there is no state for it: a keyboard and a
 * screen reader get it right for free. Confidence is not disclosed per row either. A detector that
 * was between 57% and 86% sure of all 169 segments of a song was not making 169 different
 * judgements, and 169 near-identical meters said nothing about the one thing worth knowing - so it
 * is one sentence under the card, and the number that really is per-view, how much of the recording
 * the card accounts for, is the one that gets a bar.
 *
 * A client component, unlike the rest of this page: the timeline arrived with the request, so
 * comparing the two readings is a state change rather than a refetch. A `?view=` parameter would
 * pull the object back out of the bucket on every toggle.
 */
export function ChordTimeline({ chords }: { chords: Chords }) {
  const [view, setView] = useState<View>("simple");
  const named = chords.segments.filter((segment) => segment.chord !== NO_CHORD);
  const empty = chords.segments.length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          Read from the recording by {chords.detector}, bar by bar
          {chords.key ? ` in ${chords.key}` : ""}. Times are when each chord starts.
        </p>
        {empty ? null : <ViewToggle view={view} onChange={setView} />}
      </div>

      {empty ? (
        <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
          This recording has no chords in it at all. That is usually a percussion or spoken-word
          track, and it is not an error - the tempo, key and MIDI were still measured.
        </p>
      ) : (
        <>
          <Card chords={chords} view={view} />
          <Confidence chords={chords} named={named} />
          <ol className="divide-y rounded-lg border">
            {chords.segments.map((segment) => (
              <Row key={`${segment.start_ms}-${segment.chord}`} segment={segment} view={view} />
            ))}
          </ol>
          <Rests count={chords.segments.length - named.length} />
        </>
      )}
    </div>
  );
}

/** Which of the two readings of the timeline is on screen. */
type View = "simple" | "detected";

const VIEWS: { view: View; label: string; hint: string }[] = [
  {
    view: "simple",
    label: "Simple",
    hint: "Every chord as the triad underneath it",
  },
  {
    view: "detected",
    label: "As detected",
    hint: "The labels the detector produced, extensions and inversions included",
  },
];

/** Every row: a time, a label, how long it is held, and the space between them. */
const ROW = "flex items-center gap-3 p-3";

/**
 * One stretch of the song.
 *
 * The row is a `<details>` exactly when the reading on screen is not the one the detector produced
 * and the two disagree about this chord - the only case where anything is behind the label. Nothing
 * is disclosed in the detected view: there, every row already says what was heard.
 */
function Row({ segment, view }: { segment: Segment; view: View }) {
  const silent = segment.chord === NO_CHORD;
  const label = view === "simple" ? segment.label_simple : segment.chord;
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
            className="shrink-0 text-[10px] text-muted-foreground group-open:rotate-180"
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
        "inline-flex min-w-16 justify-center rounded-md border px-2 py-0.5 font-mono text-sm font-medium",
        silent
          ? "border-dashed border-border text-muted-foreground"
          : "border-transparent bg-secondary text-secondary-foreground",
      )}
    >
      {silent ? "rest" : label}
    </span>
  );
}

/**
 * The chords this reading says the song is made of, and how much of the recording they account for.
 *
 * Both come from the API - the digest's own ranking beside `coverage`, or the ranking derived from
 * the simplified labels beside `coverage_simple` - so nothing is ranked twice. The coverage is the
 * number here worth a bar, where a per-row confidence was not: it is a share of a whole, and the
 * difference between a card accounting for 92% of a recording and one accounting for 59% is the
 * difference between a description of a song and a list of its landmarks.
 */
function Card({ chords, view }: { chords: Chords; view: View }) {
  const card = cardOf(chords, view);
  const percent = Math.round(card.coverage * 100);

  if (card.chords.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Made of</span>
        {card.chords.map((chord) => (
          <span
            key={chord}
            className="rounded-md bg-secondary px-2 py-0.5 font-mono text-secondary-foreground"
          >
            {chord}
          </span>
        ))}
      </p>
      <div className="flex items-center gap-2">
        <Progress
          value={percent}
          className="h-1.5 w-40"
          aria-label={`These chords account for ${percent} percent of the recording`}
        />
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {percent}% of the recording
        </span>
      </div>
    </div>
  );
}

/**
 * How sure the detector was, in one sentence rather than a meter on every row.
 *
 * The level is the digest's own `confidence`: the worker's mean over the segments that named a
 * chord. It is deliberately not worked out again here, because a second mean would be a second
 * definition of it. The spread is read off the rows, and is the part a mean cannot give: whether
 * every bar was equally unsure or one bar was lost. A narrow band is a detector guessing
 * throughout; a wide one is a detector that knows which bars it got.
 */
function Confidence({ chords, named }: { chords: Chords; named: Segment[] }) {
  const mean = chords.summary["confidence"];

  if (named.length === 0 || typeof mean !== "number") {
    return null;
  }

  const percents = named.map((segment) => Math.round(segment.confidence * 100));
  const lowest = Math.min(...percents);
  const highest = Math.max(...percents);
  const spread = lowest === highest ? `${lowest}%` : `${lowest}% to ${highest}%`;

  return (
    <p className="text-xs text-muted-foreground">
      Mean confidence {Math.round(mean * 100)}%, and {spread} on every chord it named.
    </p>
  );
}

/** How much of the recording had nothing in it, said the way the rows draw it. */
function Rests({ count }: { count: number }) {
  if (count === 0) {
    return null;
  }

  return (
    <p className="text-xs text-muted-foreground">
      {count === 1 ? "One stretch" : `${count} stretches`} of this recording had no chord in it,
      shown as <span className="font-mono">rest</span>.
    </p>
  );
}

/**
 * The two readings, side by side.
 *
 * Buttons rather than a control of its own, and this app's own `Button` rather than a new
 * primitive: two states with one of them on is what `aria-pressed` describes.
 */
function ViewToggle({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <div role="group" aria-label="Chord labels" className="inline-flex items-center gap-1">
      {VIEWS.map((option) => (
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
 * One reading's card: the chords, and the share of the recording they account for.
 *
 * The API decides both, so nothing is ranked twice here - and a timeline stored before the digest
 * held a progression has no ranking, which is simply no card.
 */
function cardOf(chords: Chords, view: View): { chords: string[]; coverage: number } {
  if (view === "detected") {
    return { chords: strings(chords.summary["progression"]), coverage: chords.coverage };
  }

  return { chords: chords.progression_simple, coverage: chords.coverage_simple };
}

/** A list of labels out of the digest, when the row holds one. */
function strings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((chord): chord is string => typeof chord === "string" && chord !== NO_CHORD);
}

/** A timestamp as m:ss, which is how anyone thinks about a song. */
function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** How long a chord is held, to a tenth of a second. */
function held(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}
