import { NO_CHORD, type Chords, type Segment } from "@myband/shared";

import { cn } from "@/lib/utils";

/**
 * A song's chords, in order, as the one thing a reader wants from them: what is played when.
 *
 * Five facts per row, and none of them needs the audio - when the chord starts, what it is, how long
 * it is held, how sure the detector was, and where the recording had nothing in it. The confidence
 * is shown rather than hidden because `Fmaj7` and `F` are the same three notes plus an argument:
 * a reader who can see 0.6 beside a label knows to treat the extension as a suggestion.
 *
 * Rendered on the server, like everything else on this page - the timeline arrived with the request,
 * so there is no spinner and no effect. A rest is rendered as a rest and not as a chord, because a
 * stretch with no chord in it is a fact about the recording rather than a failure to read it.
 */
export function ChordTimeline({ chords }: { chords: Chords }) {
  if (chords.segments.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
        This recording has no chords in it at all. That is usually a percussion or spoken-word
        track, and it is not an error - the tempo, key and MIDI were still measured.
      </p>
    );
  }

  const rests = chords.segments.filter((segment) => segment.chord === NO_CHORD).length;

  return (
    <div className="space-y-3">
      <ol className="divide-y rounded-lg border">
        {chords.segments.map((segment) => (
          <li key={`${segment.start_ms}-${segment.chord}`} className="flex items-center gap-3 p-3">
            <time className="w-12 shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
              {clock(segment.start_ms)}
            </time>
            <ChordLabel segment={segment} />
            <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
              {held(segment.end_ms - segment.start_ms)}
            </span>
            <ConfidenceMeter confidence={segment.confidence} />
          </li>
        ))}
      </ol>

      {rests > 0 ? (
        <p className="text-xs text-muted-foreground">
          {rests === 1 ? "One stretch" : `${rests} stretches`} of this recording had no chord in it,
          shown as <span className="font-mono">rest</span>.
        </p>
      ) : null}
    </div>
  );
}

/** The chord itself, with a rest drawn as the absence of one rather than as a label. */
function ChordLabel({ segment }: { segment: Segment }) {
  const silent = segment.chord === NO_CHORD;

  return (
    <span
      className={cn(
        "inline-flex min-w-16 justify-center rounded-md border px-2 py-0.5 font-mono text-sm font-medium",
        silent
          ? "border-dashed border-border text-muted-foreground"
          : "border-transparent bg-secondary text-secondary-foreground",
      )}
    >
      {silent ? "rest" : segment.chord}
    </span>
  );
}

/**
 * How sure the detector was, as a bar with the percentage beside it.
 *
 * The number is in the accessible name as well as the title, so it is not information only a mouse
 * can reach - and it is the only thing on the row that is a judgement rather than a fact.
 */
function ConfidenceMeter({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);

  return (
    <span
      className="flex w-20 shrink-0 items-center gap-1.5"
      title={`${percent}% confident`}
      aria-label={`${percent} percent confident`}
    >
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <span className="block h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </span>
      <span className="w-6 text-right font-mono text-[10px] text-muted-foreground tabular-nums">
        {percent}
      </span>
    </span>
  );
}

/** The chords the song is made of, when the row's digest has them. */
export function ChordProgression({ chords }: { chords: Chords }) {
  const ranked = progressionOf(chords);

  if (ranked.length === 0) {
    return null;
  }

  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Made of</span>
      {ranked.map((chord) => (
        <span
          key={chord}
          className="rounded-md bg-secondary px-2 py-0.5 font-mono text-secondary-foreground"
        >
          {chord}
        </span>
      ))}
    </p>
  );
}

/**
 * The digest's progression, when the row holds one.
 *
 * Read from the summary rather than recomputed from the segments: the worker already ranked these by
 * how much of the song each chord occupies, and a second implementation here would be a second answer
 * to the same question. A timeline stored before the field existed simply has no row.
 */
function progressionOf(chords: Chords): string[] {
  const held = chords.summary["progression"];

  if (!Array.isArray(held)) {
    return [];
  }

  return held.filter((chord): chord is string => typeof chord === "string" && chord !== NO_CHORD);
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
