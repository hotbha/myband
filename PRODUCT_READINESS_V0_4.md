# Product readiness: v0.4

The state of the product at the **0.4 freeze** (song sections), assessed surface by surface. This is a
verdict document, not a plan: [NEXT_3_RELEASES.md](NEXT_3_RELEASES.md) is what follows from it, and
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) remains the register of risks and gates.

**Release under assessment:** `main` at `440cc98` (`v0.3-midi-window`) with the sections work
uncommitted in the working tree - 28 paths, none staged. It becomes `v0.4-sections` when the commit
and tag commands in the audit are run, and it is **pre-beta**: there are no users yet, and the ten
beta seats `apps/web/features/marketing/demo-analysis.ts` mentions are not filled.

## How the verdicts are meant to be read

| Verdict       | Means                                                                                                                                               |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **READY**     | Works end to end, says only what was measured, covered by tests, and no known defect a beta user would report.                                      |
| **LIMITED**   | Works end to end and its claims are true, but there is a **measured** gap a meaningful share of beta users will hit, or a known missing capability. |
| **NOT READY** | Would mislead a stranger, or does not work.                                                                                                         |

READY and LIMITED are both shippable. The distinction is coverage, not honesty - which is why
`SECTIONS_VALIDATION.md` can answer "can sections be trusted? **YES**" while this document records
sections as **LIMITED**: a feature can be trustworthy and still answer only part of the question.

## What was verified for this assessment (and how)

Run during the audit, on this working tree:

| Check                                                        | Result                                                                                         |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `python -m pytest` in `apps/api` (worker + audio + database) | **282 passed, 1 skipped, 8 warnings in 43.85 s**                                               |
| the sections chain specifically, five suites                 | **34 passed, 1 skipped**, exit 0                                                               |
| the end-to-end chain, read file by file                      | detector -> digest -> object + row -> stage -> worker -> route -> schema -> panel, all present |
| `git status --porcelain`                                     | 28 paths (23 modified, 5 new), none staged; nothing stray                                      |
| secrets in the change                                        | 0 matches for env/secret-shaped paths; only `.env.example` files are tracked                   |

`pnpm lint`, `pnpm typecheck` and `pnpm build` were clean at the freeze verification for this branch
(the build is what catches a bad Server Component, and the song page is one). The web app has no test
runner by decision (risk R7), so every web claim below rests on reading the components, the build, and
the manual checklist in `PRODUCTION_READINESS.md`.

## Verdicts

| #   | Surface      | Verdict     | One-line reason                                                                              |
| --- | ------------ | ----------- | -------------------------------------------------------------------------------------------- |
| 1   | BPM          | **READY**   | A single measured tempo per song, stated as exactly that, with no known failure              |
| 2   | Key          | **READY**   | 24-key correlation, its strength shown, and a cross-check against a second row               |
| 3   | Chords       | **READY**   | Whole-song timeline with confidence that travels with every segment                          |
| 4   | Sections     | **LIMITED** | Trustworthy form (`A B A`) but letters only, a 4 s grid, an 8 s floor, and no real-audio run |
| 5   | MIDI         | **LIMITED** | Monophonic sketch of the opening that follows the bass; no ground truth for note correctness |
| 6   | Landing Page | **LIMITED** | Honest and checkable, but one stale claim and a demo panel a release behind                  |
| 7   | Dashboard    | **LIMITED** | Upload, progress and download work; a failed job is still a dead end                         |
| 8   | Song Page    | **READY**   | Four artifacts, each fetched independently, each honest about what it is                     |

**Tally: 4 READY, 4 LIMITED, 0 NOT READY.** No surface would mislead a stranger, and no surface is
blocked from the beta. Three of the four LIMITED verdicts are one release of work away from READY
(#4, #5, #6); the fourth (#7) is a product decision about retries.

## The measurements

### 1. BPM - READY

`analysis.detect_tempo` (`librosa.beat.beat_track`) runs over the whole recording; the result is a
column on `songs` and a tile on the song page whose hint says "one tempo for the whole song".
`tests/test_worker_analysis.py` holds it to a 120 BPM click track, and real rows exist: 117.45 BPM
with 631 beats (Tera Suroor), 89.1 (Jyoti), 107.67 (Ganesha).

**The gap:** one number per song means no tempo map, no time signature and no downbeat - a track that
opens at half-time reports one of the two readings, and there is no confidence attached to the number.
That is a documented de-scope rather than a defect, and the UI does not imply otherwise.

### 2. Key - READY

Krumhansl-Schmuckler over `chroma_cqt`, 24 keys correlated; `analysis.detect_key` returns the winner
and its strength, and `test_worker_analysis` pins A minor and C major. The interface does two things
most products do not: it shows the strength, and the song page's key hint compares the key against the
key the _chord reader_ reported (`keyHint`), saying "confirmed by the chord reader" only when two
independent rows agree, and naming both values when they disagree. The landing page quotes the honest
case - a 62-second clip whose key came back 0.26 strong.

**The gap:** one key per song, so a modulating track reports its dominant key; and the strength is a
correlation, not a probability a user should be told it is.

### 3. Chords - READY

Chroma CQT for the whole song -> chord templates -> a Viterbi pass with an explicit no-chord state.
Real measurements: 170 segments at 74.1% mean confidence on a five-minute song, and the whole-song
pass costs roughly 5 ms per second of audio (about a second of decode plus a fraction of a second of
scoring for four minutes) - cheap enough that the timeline describes the track, not its intro. An
unsure extension is reported as its parent triad (`Fmaj7` -> `F`, `EXTENSION_CONFIDENCE`), the wide
grammar stays in storage, and every segment carries its confidence to the UI. The route has three
`analysis_not_ready` refusals plus 404/401, all tested.

**The gap:** it is a reading, not a chart - voicings, inversions outside the chord's own tones, and
harmony beyond the ten qualities in `chord_templates.py` are outside its grammar; and the timeline is
frame-accurate, not bar-aligned.

### 4. Sections - LIMITED

The form of the song: which stretches are the same music and in what order, as letters. Verified end
to end and covered by 18 tests; the full audit is
[SECTIONS_VALIDATION.md](SECTIONS_VALIDATION.md).

**Why LIMITED rather than READY** - the artifact is trustworthy _and_ it answers only part of the
question:

- **Letters, not names.** A user asking "where is the chorus" cannot get an answer; that needs lyrics
  and is release 0.7.
- **Resolution.** A 4 s pool and an 8 s floor mean a short bridge can merge into its neighbour and a
  boundary can sit up to four seconds from the real transition.
- **No real-audio evidence.** Every sections test is a fixture whose shape was written in advance. The
  chords and the MIDI have real recordings behind them; sections do not.
- **The failure mode is invisible.** A wrong grouping (`A B C` for a song that is `A B A`) looks exactly
  as plausible as a right one, and nothing in the payload flags it.

### 5. MIDI - LIMITED

pYIN at 11 kHz / hop 1024, a monophonic sketch of the recording up to a 120-second cap (clamped to the
recording, and the window actually used is recorded in the artifact's summary). The cap is the one
measured decision in the pipeline: `MIDI_WINDOW_REPORT.md` swept 30 / 60 / 120 / full over three real
recordings and found the 120 s window is 2.0x-4.5x the notes of the old 30 s slice for 2.8-9.1 s of
extra tracking and under 90 MiB traced, leaving the 900 s job budget two orders of magnitude of
headroom. Whole-song transcription was measured too and deliberately not shipped: 6.6x-12.7x the notes,
but up to 232 MiB traced and 31 s on the longest song. The empty-MIDI defect that motivated the Basic
Pitch spike is closed - `transition_min_prob=None` in `midi.py` turned one real recording's artifact
from 0 notes into 29 at the same window, and that fix is already in `main`.

**Why LIMITED:**

- **Monophonic and bass-following.** `docs/analysis-worker.md` records that 69% of the sketch's notes
  sit in C2-C3: it tracks the loudest fundamental, which is usually the bass, so it is not the melody a
  user may expect from a "MIDI export".
- **The tail is absent.** Anything past two minutes is not transcribed, by decision.
- **No ground truth.** Nothing in the repository says the notes are _right_; the spike's own cost table
  puts that question at 5-8 labelled recordings. `transcription.name` and `test_worker_midi.py` mean a
  real transcriber slots into a seam that exists.

### 6. Landing Page - LIMITED

The page is the most honest marketing surface in the repository, and that is a measurable claim:
`copy.ts` states two rules (nothing is claimed the product does not do; every number is one the
pipeline measured), the not-built-yet section is stamped **Planned** on every card, and the demo panel
is built from rows actually written by the worker (`demo-analysis.ts`: 117.45 BPM, C# minor, strength
0.824, 170 segments, 74.1% mean, 29 notes / 269 B, six chords in the order the API ranked them). The
FAQ answers are checkable, including the awkward one ("on one 62-second clip the key came back only
0.26 strong").

**Why LIMITED:**

- **One stale claim.** The MIDI answer still says "the first 30 seconds"; the shipped cap has been 120 s
  since `v0.3-midi-window` (`copy.ts`, the "What can the MIDI actually do?" entry).
- **A demo a release behind.** The panel is labelled `PIPELINE_VERSION = "0.2.0"` with
  `windowSeconds: 30` - honest, but a 0.2.0 run shown on a 0.4 product.
- **The newest capability is understated.** There is no Song Sections feature card, so the form only
  appears in an FAQ answer; the page sells four capabilities while the pipeline produces five.
- **No social proof, by fact:** ten beta seats, none filled.

### 7. Dashboard - LIMITED

Ships: a dropzone with client-side rules (MP3/WAV, 200 MiB, a `.flac` or an oversize file is refused
before a byte is sent), the library rail with per-row status badges that move Queued -> Starting ->
Analysing -> Analysed without a refresh, in-flight polling that stops when nothing is in flight, the
library metrics, a refresh control, and a MIDI download on succeeded rows only.

**Why LIMITED:**

- **A failed job is a dead end.** Nothing retries it (risk R3) and there is no cancel path and no
  delete; the register accepts all three for beta, but the user experience is a row that stays failed
  until they upload the file again, which creates a second song.
- **No quota or rate limit** (R5): one account can fill the bucket, so an open beta is a cost exposure.
- **No web test runner** (R7): the badges, the polling and the refusal messages are covered by the
  manual checklist, not by a test.
- Polling rather than push, which is a latency decision rather than a gap.

### 8. Song Page - READY

One song, four artifacts, each fetched independently (`loadArtifact<T>` with a shared
`ArtifactState<T>`): the overview band of measurement tiles, the chord timeline with two readings
(simple triads or the detector's own labels), the section map, and the exports (MIDI download). The
design decisions that make it READY are the honest ones: a measurement that does not exist is absent
rather than zero ("A song nobody has analysed has no tempo, and 0 BPM would be a claim that the
recording is static"); the key tile cross-checks two rows and names both when they disagree; each panel
renders its own state, so a missing artifact degrades one panel instead of blanking the page; and the
sections panel states in words that a letter is not a name and that confidence is not displayed.

**The gap:** no web test runner, and no player - a download fetches the whole object, so there is no
ranged read for scrubbing (a documented whole-object-read decision).

## Cross-cutting findings from this audit

Three things are true of the release as a whole rather than of one surface, and none of them are code
bugs:

- **F1 - The pipeline version will be stale.** `MYBAND_PIPELINE_VERSION` is `0.3.0` in `config.py` and
  `.env.example`, and sections change the worker's output shape, so the register's own rule says bump it
  to `0.4.0`. `PRODUCTION_READINESS.md`'s gate line still says `0.2.0`. Without the bump, a stored 0.4
  row cannot be told from a 0.3 one. No test pins the value.
- **F2 - One measured decision rests on an untracked harness.** `MIDI_WINDOW_REPORT.md` cites
  `spike/basic-pitch-onnx/out/full_pipeline.py`, and `.gitignore:44` excludes `spike/`, so the harness
  behind the 120 s cap is not in the repository and a fresh clone cannot reproduce the measurement. The
  Basic Pitch evaluation itself (`results.md`, 243 lines, with its own verdict and cost table) sits
  unmerged on `refs/heads/spike/basic-pitch-onnx`.
- **F3 - The beta is uninstrumented.** `apps/web/package.json` contains no analytics dependency and no
  `track(` call exists anywhere in the app, so nothing in the product records whether a user completes
  an upload, opens a timeline, or reads a section. This matters for what to build next, not for whether
  to ship - and it is the first item of release 0.5.

## What would move each LIMITED verdict

| Surface      | The change that flips it to READY                                                             |
| ------------ | --------------------------------------------------------------------------------------------- |
| Sections     | a real-audio run over the three recordings in the local bucket, recorded; then a labelled set |
| MIDI         | note-level measurement against 5-8 labelled recordings, and the Basic Pitch decision taken    |
| Landing Page | the two copy corrections (F1's companion: the FAQ window, the demo version)                   |
| Dashboard    | a retry path for a failed row (R3), and a per-account quota (R5)                              |

None of these is a feature: the first three are measurements and copy, and with instrumentation (F3)
they make up most of release 0.5's scope in [NEXT_3_RELEASES.md](NEXT_3_RELEASES.md).
