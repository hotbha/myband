# Song sections: validation

The audit of the `sections` artifact at the **0.4 freeze**, before the release is committed or
tagged. Every claim below is either a file in this repository or a number measured on this machine
while this audit ran; where something has not been measured, the document says so and names the
check that would measure it.

**Can sections be trusted for beta users? YES** - with the limits in
[§8](#8-limitations-read-before-quoting-the-yes). Trust here means "the artifact and the interface
claim only what was measured, and nothing they say is known to be false". It does not mean the
feature answers the whole question a musician has about a song's shape; that gap is what
[PRODUCT_READINESS_V0_4.md](PRODUCT_READINESS_V0_4.md) records as **LIMITED**, and the two
statements are meant to coexist: a trustworthy artifact whose coverage is partial.

## 1. What ships

One new artifact kind, `sections`, produced for every analysed song. The chain, end to end:

| Layer           | File                                                   | Lines | What it is                                                                                       |
| --------------- | ------------------------------------------------------ | ----- | ------------------------------------------------------------------------------------------------ |
| detector        | `apps/api/app/workers/sections.py`                     | 253   | `detect_sections(path) -> SectionTimeline`; chroma in, form out                                  |
| digest          | `apps/api/app/workers/section_summary.py`              | 87    | `form`, `section_count`, `duration_ms`, `labels`, `confidence` - no librosa                      |
| storage         | `apps/api/app/workers/artifacts.py`                    | 342   | `sections_object_key`, `encode_sections`, `store_sections`, `StoredSections`, the `sections` row |
| stage           | `apps/api/app/workers/stages.py`                       | 326   | the stage, its retries, its place in the job's budget, `Produced.sections`                       |
| pipeline / loop | `apps/api/app/workers/pipeline.py`, `runner.py`        | -     | `detect_sections` wired into `Stages` and into the worker the loop builds                        |
| API             | `apps/api/app/api/routes/songs.py`                     | -     | `GET /songs/{id}/sections`                                                                       |
| API schemas     | `apps/api/app/schemas/song.py`                         | -     | `SectionOut`, `SectionsOut`, `sections_view`                                                     |
| shared contract | `packages/shared/src/analysis.ts`                      | -     | `spanSchema` -> `sectionSchema` -> `sectionsSchema`                                              |
| web client      | `apps/web/features/uploads/server-api.ts`              | -     | `fetchSections`                                                                                  |
| web renderer    | `apps/web/features/uploads/components/section-map.tsx` | 229   | the form, the lane, the rows, the honesty clause                                                 |
| web page        | `apps/web/app/songs/[id]/page.tsx`                     | -     | `SectionMap` under a `songs-heading` panel, from the shared artifact state                       |

**No migration.** `sections` was already a legal `analysis_results.kind`; the row is new data under
an existing constraint. The object lands at
`users/<user id>/analysis/<job id>/sections.json`, which satisfies
`analysis_results_object_key_check` by construction - the same key shape as `chords.json` with
another filename, asserted by
`test_the_sections_key_is_the_midi_key_under_another_filename`.

**Stored object** (`encode_sections`):

```json
{
  "detector": "chroma-pool-cluster-viterbi",
  "vocabulary": "1.0",
  "hop_ms": 4000,
  "sections": [
    { "start_ms": 0, "end_ms": 16000, "label": "A", "confidence": 1.0 },
    { "start_ms": 16000, "end_ms": 32000, "label": "B", "confidence": 1.0 }
  ]
}
```

The values above are the A-B-A fixture's own ground truth, not a measurement of a real song: three
sixteen-second stretches, and the detector is allowed one 4 s pool of tolerance on each boundary. The
shape - detector, vocabulary, the pool it compared, and a list of labelled spans - is what every object
carries; `sections` is ordered, contiguous, and starts at 0 or at whatever the first measurable frame
was.

**Stored row digest** (`artifacts.build_results`): `{detector, vocabulary, sections: <count>,
form, confidence}` - shape, not a copy of the list. The API passes that dict through unchanged
(`SectionsOut.summary`), and the panel reads `summary["form"]` and `summary["sections"]` rather
than recomputing either, so a row and a screen cannot disagree about one song.

**Route** - `GET /songs/{id}/sections` answers `200` with `{detector, vocabulary, hop_ms, sections[],
summary}`, and refuses in the same four ways the chord timeline refuses: unknown id and another
account's id are both `404` (never `403`, which would confirm the id exists), no token is `401`, and
a song that has never been analysed, a job that wrote no `sections` row, and a row whose object is
gone all answer `analysis_not_ready`. The `hop_ms` is the **4 s pool**, not the chroma hop: it is
the grid the detector really has.

## 2. Design rationale

**It answers a question about the song, not about a moment in it.** The chords say what is played
here; sections say how the recording is built - which stretches are the same music, and in what
order. That is the fifth question a player asks after tempo, key, chords and a MIDI sketch.

**Reuse the decoder, do not write a second one.** Sections pool chroma, cluster it, and then hand
the result to `segments.py` - the same Viterbi decode, majority vote and short-span trim that chord
detection uses. One decoder for both artifacts means a decode bug is fixed once, and it is why
`docs/analysis-worker.md` can describe the two stages in one paragraph.

**The digest is a string, not a second opinion.** `form` (`A B A B C`) is built by the worker from
the list it just wrote and stored in the row, so a library row can be read on its own and no reader
has to rebuild a form from timings. One definition, one place.

**`section_summary.py` exists so `artifacts.py` never imports librosa.** Section detection needs the
audio stack, and writing the row that describes the result does not - so counting sections lives on
the same side of that line as `chord_summary.py`, and the artifact tests run without the `worker`
dependency group installed. `test_the_pipeline_tests_use_the_same_shapes_as_these_dataclasses`
keeps the audio-side dataclasses and the audio-free fakes in step.

**Determinism was a requirement, not a bonus.** A re-run of one recording must produce one answer,
so the k-means initial guess is spread evenly across the recording instead of drawn at random, the
iteration count is bounded, and nothing in the module reads a clock, a connection or the queue.
`test_the_same_recording_always_produces_the_same_sections` holds that.

**No beat or bar snapping in v1.** A boundary lands on the detector's own 4 s pool rather than on a
bar. Snapping would put a confidently wrong downbeat on every boundary instead of a slightly ragged
right one; the grid snapping would want is the one `analysis.detect_tempo` already computes.

## 3. Detector architecture

Four steps, all named algorithms, in `sections.py`:

1. **Pooling.** Chroma frames are averaged into blocks of `POOL_MS` (4000 ms, ~43 frames at the
   ~93 ms chroma hop). Two bars at a walking tempo: shorter and the detector is reading chords,
   longer and a whole verse is one block.
2. **Clustering.** Lloyd's algorithm over cosine distance into `SECTION_STATES` groups from an
   evenly spread initial guess, capped at `CLUSTER_ITERATIONS` passes or `CLUSTER_TOLERANCE`
   movement.
3. **Decoding.** `segments.py`, unchanged: log-emissions over cosine similarity
   (`EVIDENCE_PER_FRAME`) weighed against a self-transition cost (`SELF_TRANSITION`), a Viterbi
   pass, a `SMOOTHING_BLOCKS` majority vote, and short spans absorbed into a neighbour.
4. **Labelling.** Each group takes the letter of the first place it appears.

| Constant                  | Value                         | Why that value                                                                |
| ------------------------- | ----------------------------- | ----------------------------------------------------------------------------- |
| `POOL_MS` / `POOL_FRAMES` | 4000 ms / ~43 frames          | two bars at a walking tempo; the grid boundaries land on                      |
| `SECTION_STATES`          | 6                             | a ceiling, not a setting: a two-part song uses two and the rest stay empty    |
| `CLUSTER_ITERATIONS`      | 25                            | converges in a handful of passes on anything with structure in it             |
| `CLUSTER_TOLERANCE`       | 1e-6                          | bounds passes and movement both, so a pathological file cannot spin           |
| `SELF_TRANSITION`         | 0.8                           | how willing the sequence is to move                                           |
| `EVIDENCE_PER_FRAME`      | 15.0                          | a cosine is a narrow scale; this weighs evidence against a transition cost    |
| `SMOOTHING_BLOCKS`        | 3                             | one verse block that sounds like the chorus does not cut the verse in three   |
| `MIN_SECTION_MS`          | 8000                          | nothing shorter is a section; over one block, so one block is never a section |
| `EPSILON`                 | 1e-9                          | a similarity of zero has no logarithm                                         |
| `LETTERS`                 | `A..Z`                        | only ever `SECTION_STATES` of them are used                                   |
| `DETECTOR_NAME`           | `chroma-pool-cluster-viterbi` | travels into object and row, so a re-run is not mistaken for agreement        |
| `VOCABULARY_VERSION`      | `1.0`                         | the grammar the letters were assigned under                                   |

## 4. Why the labels are A and B and not verse and chorus

A section is named after the first place its group appears, so the opening is always `A`, the next
new music is `B`, and a repeat is visible as a repeat. That is the whole vocabulary: a letter means
"the same music as the other `A`", and nothing more.

The names a musician would use are not measurable from chroma. A chorus is the part with the hook;
a hook is words and a melody; this detector reads neither. Renaming a cluster "verse" would guess on
every song whose second part is a bridge, and it would guess _invisibly_ - the stored artifact would
look exactly as confident as a correct one. The decision on record is that a wrong chorus is worse
than an honest letter, and it is enforced in three places: the module docstring (`sections.py:22-27`),
the panel's own sentence ("A letter, not a name. Telling a chorus from a verse takes the lyrics, so
this says the one thing it can hear: which stretches are the same music."), and the landing page's
answer to "What do the song sections tell me?".

Two consequences worth stating plainly:

- A section carries **no `label_simple`**, unlike a chord. There is nothing to simplify about a
  letter, and inventing a simplification is the one thing that field exists to prevent.
- **`A` is not promised to be the first verse.** It is promised to be the first _thing_, whatever
  it happens to be - an intro, a count-in, a bare vocal.

## 5. What the confidence means, and what it must not be used for

`Section.confidence` is how tightly the blocks inside a section agreed with the group they were
assigned to, in 0..1. The digest's `confidence` is the mean of those over the list
(`section_summary.confidence`).

**It is not on the same scale as a chord's confidence**, and the code says so in three places
(`sections.py:96-100`, `section_summary.py:9-11`, the shared schema's `sectionSchema` docstring). A
group _is_ the mean of the blocks that make it up, so agreement with it is high by construction: a
section is never reported at 0.4 the way a chord can be. It compares one section of one song with
another section of the same song, and that is the only comparison it supports.

The interface decision that follows from that: **the panel does not display it.** `section-map.tsx`
renders the form, the lane, the rows and the count, and reads only `summary["form"]` and
`summary["sections"]` - a number that is high for a correct detection and high for a wrong one,
shown in a badge, reads as quality. The API still publishes it (`SectionOut.confidence`, parsed by
`sectionsSchema`), because it is a real measurement of a real thing and a future screen may have a
use for it; nothing in the product claims it is a grade.

Practical reading for a beta user: **trust the letters, not a per-section number** - and no such
number is offered.

## 6. Failure modes

| Situation                                                      | What the detector does                                        | What the user sees                                                                                                                      |
| -------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Silence or nothing measurable                                  | returns an empty timeline                                     | the panel's empty state: "This recording had nothing to tell apart." The tempo, key, chords and MIDI were still measured.               |
| Recording shorter than one block                               | one section, `A`, spanning the recording                      | `A` and one row - which is the truth about a three-second clip                                                                          |
| A genuine section shorter than 8 s (a turn, a tag)             | absorbed into its neighbour                                   | two real sections read as one; the form is coarser, not wrong                                                                           |
| Boundary within 4 s of the real transition                     | boundary lands on the 4 s pool, up to one block early or late | a row whose start is up to four seconds off; the order is never wrong                                                                   |
| A wrong grouping (two parts merged, one split)                 | a plausible-looking form                                      | **the worst case: `A B C` where the song is `A B A`.** Every row still looks reasonable, which is why this is listed rather than hidden |
| More than six distinguishable parts                            | six letters, the extras merged into the nearest group         | a form with at most six distinct letters                                                                                                |
| A song analysed before the digest held a form (0.1.0-era rows) | nothing to read                                               | the panel shows the list and no form - `Form` returns `null` rather than rebuilding one                                                 |
| Job failed before the sections stage                           | no `sections` row                                             | the route answers `analysis_not_ready`; the page renders that message in the panel, not an empty map                                    |
| Row present, object missing (bucket gone, lifecycle rule)      | route refuses rather than serving a lie                       | `analysis_not_ready` - same message, and the reason is in the API log                                                                   |
| Sections disabled or absent entirely                           | the job still succeeds: `bpm, key, chords, midi`              | `test_a_job_that_produced_no_sections_is_not_an_error` - a missing artifact is not a failed song                                        |
| Another account's song id                                      | not found                                                     | `404`, never `403`                                                                                                                      |

**The one failure a user cannot detect is a wrong grouping**, and there is no number in the payload
or the UI that catches it: a form like `A B C` for a song that is `A B A` is indistinguishable from
a song that really is `A B C`. That is the reason a labelled set of real recordings is the first
thing this artifact should be measured against (see [§9](#9-recommendation)), and the reason the
beta's feedback loop - not a confidence score - is what would catch it.

## 7. Test evidence

Everything below was run during this audit, on this working tree, unless a line says otherwise.

```powershell
$env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
cd apps\api
python -m pytest -p no:cacheprovider
# -> 282 passed, 1 skipped, 8 warnings in 43.85s        (the skip is test_worker_e2e,
#                                                       gated on MYBAND_E2E=1 and a bucket)
python -m pytest tests/test_worker_sections.py tests/test_song_sections.py `
                 tests/test_worker_artifacts.py tests/test_worker_pipeline.py `
                 tests/test_worker_e2e.py -q
# -> 34 passed, 1 skipped, exit 0
```

**`tests/test_worker_sections.py` - 11 tests, new.** Needs the audio group.

| Test                                                               | What it holds                                                                              |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| `test_the_repeat_comes_back_as_a_repeat`                           | the 48 s A-B-A fixture comes back `A B A`, and the vocabulary is `("A", "B")`              |
| `test_each_section_lands_where_it_was_played`                      | starts match 0 / 16000 / 32000 ms within `abs=POOL` - the grid admits its own resolution   |
| `test_the_sections_cover_the_recording_without_gaps_or_overlaps`   | consecutive sections, `next.start == last.end`, nothing missing                            |
| `test_the_timeline_says_which_detector_made_it`                    | name and vocabulary travel with the list                                                   |
| `test_the_same_recording_always_produces_the_same_sections`        | a re-run is byte-identical in shape - the determinism claim                                |
| `test_a_section_may_hold_several_chords`                           | a section is not a chord: a 16 s block containing four chords is one section               |
| `test_silence_has_no_sections_to_find`                             | silence yields `()` and `form == ""`, not one fabricated `A`                               |
| `test_a_recording_shorter_than_one_block_is_one_section`           | a 2 s clip is one section, `0..~2000 ms`                                                   |
| `test_the_digest_describes_the_sections_it_was_given`              | count 4, duration 16000, `form == "A B A C"`, labels `("A","B","C")`, mean confidence 0.75 |
| `test_an_empty_list_digests_to_nothing_rather_than_to_zero`        | every digest reader has a defined answer for `()`                                          |
| `test_the_pipeline_tests_use_the_same_shapes_as_these_dataclasses` | `tests/fakes.py` mirrors the dataclasses field for field                                   |

**`tests/test_song_sections.py` - 7 tests, new.** Needs a database; asserts the body a browser would
receive, and builds its rows with the worker's own `artifacts.build_results` so the route and the
worker cannot disagree about where a list lives.

`test_an_analysed_song_hands_back_its_sections` (200 with list and digest; `summary["form"] == "A B
A"`, `summary["sections"] == 3`), `test_the_summary_is_the_stored_row_and_not_a_recomputation`,
`test_a_song_that_has_never_been_analysed_is_not_ready`,
`test_a_job_that_produced_no_sections_is_not_an_error` (200 with an empty list),
`test_sections_whose_object_is_gone_are_not_ready`, `test_an_unknown_song_is_not_found`,
`test_a_request_without_a_token_is_refused`.

**The rest of the chain, updated in the same release.** `test_worker_artifacts.py` (10 tests, 2 new)
covers the key shape `.../sections.json`, that storing writes the list and digests it, and that a
job's rows are exactly `bpm, key, chords, sections, midi`. `test_worker_pipeline.py` (6) asserts the
bytes, the `application/json` content type, and the row's summary
(`{detector, vocabulary, sections: 3, form: "A B A", confidence}`). `test_worker_e2e.py` walks
presigned PUT to five rows including the sections row. `tests/fakes.py` gained
`FakeSection`/`FakeSectionTimeline` and `worker_support.py` scripts the new stage, which is what lets
the pipeline, artifact and route suites run without an audio stack.

**What the tests do not cover** is the rest of `§8`, and it is worth being blunt about the shape of
the evidence: **every sections test is a fixture whose shape was decided in advance** - two chords
alternating in A minor/F, then C/G, then the first pair again. It is the right instrument for
"does the detector find a repeat that is really there", and it says nothing about a real mix.

## 8. Limitations, read before quoting the YES

| Id  | Limitation                                                                                                                                                                                                                                                                       | Cost to close                                                                 |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| L1  | **Evidence is synthetic.** The detector has never been run against a real recording in this repository; chords and MIDI have (170 segments / 74.1% mean on a real song; three real recordings in [MIDI_WINDOW_REPORT.md](MIDI_WINDOW_REPORT.md)).                                | hours - a read-only run over the three recordings already in the local bucket |
| L2  | **No ground truth for form.** "Is `A B A` right for this song" has never been asked against an annotated answer; the standing note from the MIDI spike applies here too: the next question is an ear, then a small labelled set.                                                 | 2-3 days, shared with the MIDI work                                           |
| L3  | **No bar or beat snapping** (deliberate): boundaries are on a 4 s grid, not on the downbeat `detect_tempo` already computes.                                                                                                                                                     | days, and it needs L2 to judge                                                |
| L4  | **Short sections merge** - 8 s floor, 4 s resolution. A four-bar bridge can vanish into its neighbour.                                                                                                                                                                           | configuration, then L2                                                        |
| L5  | **Six groups maximum**, so a seven-part song reads as six.                                                                                                                                                                                                                       | hours, then L2                                                                |
| L6  | **Confidence is not a quality score** and is not shown; agreement with a cluster mean is high by construction.                                                                                                                                                                   | by design                                                                     |
| L7  | **No naming.** Letters, not verse/chorus. A user who wants to click "Chorus" cannot.                                                                                                                                                                                             | release 0.7, needs a second signal (lyrics/arrangement)                       |
| L8  | **No web test runner** (risk R7), so the panel is covered by the manual checklist and by `pnpm build`, not by a test.                                                                                                                                                            | toolchain decision, deliberately deferred                                     |
| L9  | Two files over the 300-line soft target: `artifacts.py` 342, `stages.py` 326. Accepted as cohesive, and consistent with `services/storage.py` 356 and `models/analysis_job.py` 414.                                                                                              | a refactor with no user-visible effect                                        |
| L10 | **The release will record `MYBAND_PIPELINE_VERSION=0.3.0`** for a 0.4 song unless the setting is bumped, so stored rows cannot be told apart from pre-sections ones - even though the register's own rule is "bump it when the worker's output shape changes".                   | one line, see §9                                                              |
| L11 | `midi.py`'s docstring still says basic-pitch "cannot be installed here", which the `spike/basic-pitch-onnx` measurements refined (the ONNX export ships in the wheel; the crash is an Anaconda base-interpreter issue, not the model).                                           | one paragraph, see §9                                                         |
| L12 | The MIDI window decision in [MIDI_WINDOW_REPORT.md](MIDI_WINDOW_REPORT.md) cites `spike/basic-pitch-onnx/out/full_pipeline.py`, and `spike/` is in `.gitignore` (line 44), so **the harness behind that decision is not in the repository** - a fresh clone cannot reproduce it. | a decision about where harnesses live                                         |

L1 is the one that matters for beta, and it is also the cheapest to close.

## 9. Recommendation

Before the release is tagged (hours of work, no new features, all of it release hygiene):

1. **Bump `MYBAND_PIPELINE_VERSION` to `0.4.0`** - `apps/api/app/core/config.py`,
   `apps/api/.env.example`, and the gate line in `PRODUCTION_READINESS.md` that still says `0.2.0`.
   No test pins `0.3.0` (`test_upload_flow.py` compares against the setting), so this is three lines
   and no test churn.
2. **Fix the stale MIDI claim on the landing page** - `apps/web/features/marketing/copy.ts` answers
   "What can the MIDI actually do?" with "the first 30 seconds", and the cap has been 120 s since
   `v0.3-midi-window`. The page's own rule is that every number is one the pipeline measured.
3. **Run the detector over real audio** and record the forms: the three recordings in the local
   bucket are already in the MIDI report, and reading them is a read-only run plus a place to write
   the answer down. This turns L1 from "unmeasured" into a number.
4. **Decide what happens to `spike/basic-pitch-onnx`** (L12, and the recommendation in
   [NEXT_3_RELEASES.md](NEXT_3_RELEASES.md)): its `results.md` is the only Basic Pitch measurement in
   existence and it is on an unmerged branch that `main`'s `.gitignore` excludes.
5. **Leave the letters alone.** Naming is a product decision that needs lyrics and ground truth, not
   a detector tweak, and doing it now would replace an honest artifact with a fluent wrong one.

After the beta: if users ask "where is the chorus", that is release 0.7, and it should be built on a
labelled set rather than on intuition.

## 10. Can sections be trusted for beta users?

**YES.**

The evidence, in the order it should be weighed:

- **The chain is verified end to end**, not asserted: detector (`sections.py`) -> digest
  (`section_summary.py`) -> object and row (`artifacts.py`) -> stage (`stages.py`) -> worker
  (`runner.py`) -> `GET /songs/{id}/sections` -> `SectionsOut` -> `sectionsSchema` -> `SectionMap` on
  the song page. Each hop was read during this audit, and each hop has a test.
- **18 dedicated tests pass** (11 detector, 7 route) plus assertions in the artifact, pipeline and
  end-to-end suites; the full API, worker and database suite is **282 passed, 1 skipped in 43.85 s**,
  the skip being the end-to-end case gated on `MYBAND_E2E=1`.
- **The repeat is found where a repeat was written**: the A-B-A fixture comes back `A B A`, and the
  boundaries land within one 4 s block of where the music changed.
- **Determinism is structural, not observed**: no RNG, a bounded iteration count, a fixed tolerance,
  and an initial guess spread evenly over the recording - so two runs cannot disagree about one file.
- **It declines to guess**: silence produces no sections rather than one called `A`; a section can
  never be a single 4 s block; the object and the row both carry the detector's name and vocabulary
  version, so a re-run is never mistaken for agreement; and the one thing it cannot measure - the
  words - it does not name.
- **The interface claims exactly what the artifact claims.** The panel's own sentence and the landing
  page's answer both say "a letter, not a name", and the by-construction confidence is not rendered
  anywhere.

The bounds of that YES: the evidence is synthetic until §9.3 is done, the form has no annotated
ground truth, boundaries sit on a 4 s grid, sections under 8 s merge, and a wrong grouping would look
plausible. None of those make a stored form _false_ - they bound how much of a musician's question it
answers. A beta user can be shown this artifact knowing it says only what was measured;
[PRODUCT_READINESS_V0_4.md](PRODUCT_READINESS_V0_4.md) records that partial coverage as **LIMITED**,
and the way to a full **READY** is §9.3 plus a labelled set of real recordings.
