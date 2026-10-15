import { NO_CHORD, type Chords, type Segment } from "@myband/shared";

/**
 * The two readings of one chord timeline, and the small arithmetic around them.
 *
 * A module rather than part of a component because three components ask the same
 * questions and they must not answer them differently: the toggle offers the readings, the
 * lane and the rows draw them, and the summary card ranks them.
 *
 * The readings are **the same timeline**, not two analyses. **Simple** shows each chord as
 * the triad underneath it, which is what somebody playing along wants; **as detected**
 * shows the label the detector actually produced, extension and inversion included. The
 * simple reading is the default because the alternative is a wall of `Fmaj7`, `Am7` and
 * `C/E` when four chords are being played - but it is a *reading* and not a correction, so
 * the detected label is one tap away.
 *
 * Which of the two a row's two labels come from is decided by the API: `chord` is what the
 * detector heard and `label_simple` is the triad the API says to show. Nothing here
 * simplifies a chord, because that is a musical judgement and this is TypeScript.
 */
export type ChordView = "simple" | "detected";

/** The two readings, in the order the toggle offers them. */
export const CHORD_VIEWS: { view: ChordView; label: string; hint: string }[] = [
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

/** Whether this stretch had no chord in it at all. */
export function isRest(segment: Segment): boolean {
  return segment.chord === NO_CHORD;
}

/** The label this reading shows for one stretch. */
export function labelOf(segment: Segment, view: ChordView): string {
  return view === "simple" ? segment.label_simple : segment.chord;
}

/**
 * The chords this reading says the song is made of, and how much of the recording they
 * account for.
 *
 * Both halves come from the API - the digest's own ranking beside `coverage`, or the
 * ranking derived from the simplified labels beside `coverage_simple` - so nothing is
 * ranked twice and a timeline written before the digest held a progression is simply no
 * card.
 */
export function cardOf(chords: Chords, view: ChordView): { chords: string[]; coverage: number } {
  if (view === "detected") {
    return { chords: strings(chords.summary["progression"]), coverage: chords.coverage };
  }

  return { chords: chords.progression_simple, coverage: chords.coverage_simple };
}

/**
 * How sure the detector was overall, or nothing.
 *
 * The digest's own `confidence`: the worker's mean over the segments that named a chord.
 * Deliberately not recomputed here, because a second mean would be a second definition of
 * it - the spread of the individual values is computed at the call site, which is the
 * part a mean cannot give.
 */
export function meanConfidence(chords: Chords): number | null {
  const mean = chords.summary["confidence"];

  return typeof mean === "number" ? mean : null;
}

/** A list of labels out of the digest, when the row holds one. */
function strings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((chord): chord is string => typeof chord === "string" && chord !== NO_CHORD);
}

/** A timestamp as m:ss, which is how anyone thinks about a song. */
export function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** How long a chord is held, to a tenth of a second. */
export function held(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}
