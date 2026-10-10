/**
 * The music-intelligence contracts, mirrored from `apps/api`'s Pydantic models.
 *
 * `apps/api` is the source of truth: these schemas mirror its response models field for field,
 * snake_case included, so no field has to be renamed on the way between languages - the same rule
 * `uploads.ts` follows, and parsed rather than asserted so a drifted response fails loudly here
 * instead of appearing as `undefined` three components deep.
 *
 * The segment is the piece worth noticing. A chord timeline and a section list are the same shape
 * of data - a start, an end, a label, and how sure the detector was - so they share one schema, and
 * in the interface one renderer.
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
 * One labelled stretch of a song: a chord today, a section next.
 *
 * `chord` is a name from the API's closed vocabulary (`Am`, `Fmaj7`, `C/E`) or `"N"`, which is not
 * a chord at all but the word for "nothing was played" - a fact about the recording rather than a
 * failure to read it. `confidence` is the detector's own similarity, in 0..1.
 *
 * `label_simple` is the label to *show*: the same chord as its triad, decided by the API so that no
 * reader has to know that `Fmaj7` is `F`, or why. It is required rather than optional because every
 * labelled stretch the API serves carries one, and a browser that could not find it would have to
 * invent a simplification - which is the one thing this field exists to prevent.
 */
export const segmentSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  chord: z.string().min(1),
  label_simple: z.string().min(1),
  confidence: z.number().min(0).max(1),
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
