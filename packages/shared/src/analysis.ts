/**
 * The music-intelligence contracts, mirrored from `apps/api`'s Pydantic models.
 *
 * `apps/api` is the source of truth: these schemas mirror its response models field for field,
 * snake_case included, so no field has to be renamed on the way between languages - the same rule
 * `uploads.ts` follows, and parsed rather than asserted so a drifted response fails loudly here
 * instead of appearing as `undefined` three components deep.
 *
 * The span is the piece worth noticing. A chord segment and a section are the same shape of data -
 * a start, an end and how sure the detector was - so they share one schema, and in the interface
 * one renderer. What differs is the label: a chord is a name from a closed grammar, and a section
 * is a letter that says which stretches are the same music.
 */
import { z } from "zod";

/**
 * The label for "nothing was played here".
 *
 * Not a chord with no extension - the absence of one - which is why it is spelled here rather than
 * being left for each caller to invent. The API's `workers.chord_summary.NO_CHORD` is the authority.
 */
export const NO_CHORD = "N";

/**
 * The part of a labelled stretch that both artifacts share: when it is, and how sure the detector
 * was.
 *
 * Split out rather than copied so the two schemas cannot drift into disagreeing about what a
 * timestamp is - and so a renderer written against a span can draw either artifact.
 */
const spanSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  confidence: z.number().min(0).max(1),
});

/**
 * One chord, held for a stretch of the song.
 *
 * `chord` is a name from the API's closed vocabulary (`Am`, `Fmaj7`, `C/E`) or `"N"`, which is not
 * a chord at all but the word for "nothing was played" - a fact about the recording rather than a
 * failure to read it.
 *
 * `label_simple` is the label to *show*: the same chord as its triad, decided by the API so that no
 * reader has to know that `Fmaj7` is `F`, or why. It is required rather than optional because every
 * labelled stretch the API serves carries one, and a browser that could not find it would have to
 * invent a simplification - which is the one thing this field exists to prevent.
 */
export const segmentSchema = spanSchema.extend({
  chord: z.string().min(1),
  label_simple: z.string().min(1),
});

/**
 * One section: a stretch of the song, and the letter it shares with the stretches that repeat it.
 *
 * `label` is a letter and not a name, on purpose. `A` means "the same music as the other A", which
 * is what a detector can measure; calling it verse or chorus would take the lyrics. That is also
 * why a section carries no `label_simple`: there is nothing to simplify about a letter.
 *
 * `confidence` is how tightly the section's blocks agreed with the group they were put in - and it
 * is not the same scale as a chord's. A group is the mean of the blocks that make it up, so
 * agreement is high by construction; it compares one section with another, not a section with a
 * chord.
 */
export const sectionSchema = spanSchema.extend({
  label: z.string().min(1),
});

/**
 * A song's section list (`GET /songs/{id}/sections`).
 *
 * The list itself rather than a link to it, like the chord timeline and unlike the MIDI: a screen
 * renders this, so the API is the thing that reads the object.
 *
 * `summary` is the digest the worker wrote into `analysis_results`, passed through unchanged - the
 * same rule the timeline follows, and deliberately loose for the same reason. The form (`A B A B C`)
 * lives in it rather than here, because it is the worker's statement about the list it wrote;
 * anything that needs one reads it where it is used rather than rebuilding it.
 *
 * `hop_ms` is the pool the detector compared, not its chroma frame: four seconds of music per
 * block, which is the grid a boundary can land on. A renderer that draws the boundaries is drawing
 * exactly that resolution.
 */
export const sectionsSchema = z.object({
  detector: z.string().min(1),
  vocabulary: z.string().min(1),
  hop_ms: z.number().int().positive(),
  summary: z.record(z.string(), z.unknown()),
  sections: z.array(sectionSchema),
});

/**
 * A song's chord timeline (`GET /songs/{id}/chords`).
 *
 * The timeline itself rather than a link to it, which is the one way this differs from the MIDI:
 * a screen renders this, so there is nothing to download and nothing to expire.
 *
 * `summary` is the digest the worker wrote into `analysis_results`, passed through by the API
 * unchanged - so it is deliberately loose here. Which fields it holds is the worker's contract with
 * the library, not this screen's; a screen that needs one of them parses it where it is used, and a
 * timeline written before a field existed still renders.
 *
 * The two cards sit beside it, and they are the API's: `coverage` is how much of the recording the
 * chords in `summary.progression` account for, and `progression_simple` with `coverage_simple` is
 * the same reading built from every row's `label_simple`. Both are read here rather than derived -
 * the API has already answered the question twice, and a third answer in a browser would be a third
 * opinion about one song.
 */
export const chordsSchema = z.object({
  detector: z.string().min(1),
  vocabulary: z.string().min(1),
  key: z.string().nullable(),
  hop_ms: z.number().int().positive(),
  summary: z.record(z.string(), z.unknown()),
  coverage: z.number().min(0).max(1),
  progression_simple: z.array(z.string().min(1)),
  coverage_simple: z.number().min(0).max(1),
  segments: z.array(segmentSchema),
});

export type Segment = z.infer<typeof segmentSchema>;
export type Chords = z.infer<typeof chordsSchema>;
export type Section = z.infer<typeof sectionSchema>;
export type Sections = z.infer<typeof sectionsSchema>;
