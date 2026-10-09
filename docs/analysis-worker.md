# The analysis worker

The objective in one sentence: a song sitting in `analysis_jobs` as `queued` comes out of this
process with **duration, BPM, key, a chord timeline and a MIDI artifact** stored against it, and the
job row says `succeeded` - or it says `failed` with a reason somebody can act on.

```bash
python -m app.workers [--once] [--max-jobs N]
```

A standalone process, not a route and not a thread inside the API. It shares the API's
settings, models and services and nothing about its lifecycle: it is started, stopped and
scaled on its own, and holds no state a restart would lose. Its dependencies are not the
API's either - the audio stack lives in a `worker` dependency group, because the API process
never decodes audio:

```bash
uv sync --project apps/api --group worker
uv run --project apps/api --group worker --directory apps/api python -m app.workers
```

`--once` drains whatever is queued and exits, which is what a cron-style deployment (and the
end-to-end test) uses. Without it the loop polls, `MYBAND_WORKER_POLL_SECONDS` apart, and
stops on Ctrl-C or SIGTERM **after** the job in hand.

## What it does, in order

```text
txn 1   claim_next (FOR UPDATE SKIP LOCKED) -> begin: queued -> running, attempts+1,
        started_at, heartbeat_at                                        COMMIT
        ── the row lock is released here, which is what makes a live heartbeat meaningful
work    download (GET) -> duration (file header) -> tempo -> key
        -> chords (whole song, chroma) -> MIDI (bounded window) -> PUT artifacts
        a heartbeat thread commits heartbeat_at on its own connection every 15s
txn 2   complete: job -> succeeded + analysis_results + songs.latest_job_id
        + songs.duration_ms / bpm / musical_key                         COMMIT
        ...or fail: job -> failed + error_code + finished_at            COMMIT
```

**Two transactions, not one**, and the gap between them is the design. A transaction held
across the analysis would make `heartbeat_at` invisible to every other session until it
committed - exactly the window the heartbeat exists to cover - and a crashed worker would
lose the work silently. Two transactions also mean the job is genuinely visible as `running`
while it is being worked on, which is what the UI polls for.

| Step          | Where                                 | Notes                                                        |
| ------------- | ------------------------------------- | ------------------------------------------------------------ |
| claim + start | `queue.claim_next`, `queue.begin`     | the row lock is the whole concurrency story                  |
| fetch         | `stages.Stages._download`             | a browser put it in R2; this is the first process to hold it |
| duration      | `analysis.read_duration_ms`           | from the container header, so no decode                      |
| tempo         | `analysis.detect_tempo`               | `librosa.beat.beat_track`                                    |
| key           | `analysis.detect_key`                 | Krumhansl-Schmuckler over `chroma_cqt`, 24 keys correlated   |
| chords        | `chords.detect_chords`                | chroma CQT -> templates -> Viterbi, over the whole song      |
| MIDI          | `midi.transcribe_with_pyin`           | a monophonic sketch of a bounded window (see below)          |
| store         | `artifacts.store_midi`, `store_chords`| `users/<uid>/analysis/<job id>/{transcription.mid,chords.json}` |
| finish        | `queue.complete`, `song.set_analysis` | one transaction, or nothing                                  |

Duration, BPM and key are **columns on `songs`** (migration 04) rather than artifacts: the
library list reads them per row, and reading them out of `analysis_results` would be a join
plus a jsonb extraction per song. The two payloads are artifacts, and their keys satisfy
`analysis_results_object_key_check` by construction. A payload's key is also what the browser ends
up reading: `GET /songs/{id}/midi` signs a short-lived GET for the `midi` row's `object_key` so the
object the worker wrote is the object the user downloads, and `GET /songs/{id}/chords` reads the
`chords` row's object directly and answers with the timeline (docs/upload-flow.md).

**Chords are read from the audio, not from the MIDI.** The only symbolic artifact this process
produces is a monophonic 30-second sketch whose notes are 69% in C2-C3 - it follows the bass - so it
cannot carry harmony, and harmony is a fact about notes sounding *together*. The pipeline is
therefore `analysis.py` (measure) -> `chroma.py` (fold the spectrum into twelve pitch classes per
frame, over the whole song) -> `chords.py` (score every frame against every chord in
`chord_templates.py`, then decode the most likely *sequence* of labels with a Viterbi pass and an
explicit no-chord state). `segments.py` is the shared machinery underneath - scores to a path, a
path to spans - because section detection will want exactly the same steps.

Two decisions inside that are worth knowing before reading the code:

- **Confidence-aware simplification.** The grammar is ten qualities over twelve roots (`maj`, `m`,
  `dim`, `aug`, `sus2`, `sus4`, `maj7`, `m7`, `7`, `m7b5`, plus `/<bass>`), and a segment whose
  confidence is below `EXTENSION_CONFIDENCE` is reported as its parent triad - `Fmaj7` as `F`,
  `Am7` as `Am`, `Gsus4` as `G` - because a speculative seventh is a worse answer than a certain
  triad. The wide grammar is kept in storage so a later fretboard or section feature never has to
  rewrite a timeline that was already written.
- **No beat or bar snapping in v1.** Segments are frame-accurate (a ~93 ms hop). Snapping would put
  a confidently wrong downbeat on every segment instead of a slightly ragged right one, and the grid
  a section detector would want is the one `analysis.detect_tempo` already computes.

Where the code lives: `app/workers/` - `runner.py` (the loop), `pipeline.py` (one job's
lifecycle), `stages.py` (the work, its retries and its budget), `analysis.py`, `chroma.py`,
`chords.py`, `chord_templates.py`, `chord_summary.py`, `segments.py`, `midi.py`, `artifacts.py`,
`heartbeat.py`, `errors.py`, `tuning.py`.

## Measured cost

Real numbers from this machine, on 4 s of 22 kHz audio. The thing to know is that the pitch
tracker, not the detectors, is what a job's budget is spent on:

| Stage                   | Time            | Note                                            |
| ----------------------- | --------------- | ----------------------------------------------- |
| duration                | ~0 ms           | header only                                     |
| decode                  | ~0.1 s          | whole file, mono, 22.05 kHz                     |
| tempo + key             | ~0.5 s          | the full recording                              |
| chords (whole song)     | ~5 ms per second of audio | `chroma_cqt` + a 121-state Viterbi; ~2 s of numba compile is a one-off |
| pYIN (hop 512)          | **14.7 s**      | ~3.7x realtime - the reason for the window      |
| pYIN (11 kHz, hop 1024) | ~1 s per second | what `MYBAND_WORKER_MIDI_WINDOW_SECONDS` bounds |

So the MIDI is transcribed from the **first `window_seconds`** (default 30) rather than the
whole song: a monophonic sketch of the intro in tens of seconds beats a perfect transcription
that never finishes. The window that was used is recorded in the artifact's summary.

The chords are the opposite case, and that is the point of doing them here. Measured on a warm
process, four minutes of audio costs about a second of decode-and-chroma and under a fifth of a
second for the scoring, the Viterbi pass and the segments together - so the timeline can be built
from the **whole song**, and it describes the track rather than its intro. The pitch tracker is
what a job's budget actually goes on; everything else in this list is noise beside it.

## When something goes wrong

| Code                  | Permanent? | What it means                                                        |
| --------------------- | ---------- | -------------------------------------------------------------------- |
| `source_missing`      | yes        | the object is not in the bucket, and will not appear                 |
| `decode_error`        | yes        | not audio this pipeline can read, or empty                           |
| `unanalyzable`        | yes        | readable, but nothing measurable in it (silence)                     |
| `analysis_timeout`    | yes        | the job spent its whole budget (`MYBAND_WORKER_JOB_TIMEOUT_SECONDS`) |
| `storage_unavailable` | **no**     | the bucket is down or slow; retried in-process                       |
| `storage_rejected`    | yes        | the bucket answered and refused: a policy problem, not a blip        |
| `internal_error`      | yes        | a bug; the message carries the exception's class                     |
| `stale`               | -          | written by the _sweep_, for a worker that stopped reporting          |

Transient failures are retried in-process with a growing backoff, up to
`MYBAND_WORKER_MAX_ATTEMPTS`. Everything else fails the job at once. Nothing escapes the
pipeline: even an unhandled exception ends as a failed job, because a job left in `running`
with no explanation costs a fifteen minute reap and tells nobody what went wrong.

A retry is **not** a new job row - `attempts` stays where `begin` put it, so one dispatch is
still one billable unit. Only a _terminal_ job is retried, and that means queueing a new one.

## Heartbeats, reaping and idempotency

- The heartbeat is a thread with its **own connection** per beat, because a beat written on
  the job's connection would stay invisible until the job committed. It stops when the job is
  no longer in flight, and it swallows its own database errors: the lease is 15 minutes and
  the interval 15 seconds, so several missed beats are expected to be harmless.
- A process that was killed cannot fail its own job, so the loop calls `queue.reap_stale` on
  its own schedule and once at startup. Jobs are **failed**, not requeued - starting a new
  attempt behind a user's back is a product decision, not something a sweep should make.
- The lease starts when a job is **dispatched**, so the sweep only ever looks at `dispatched`
  and `running`. Those are the statuses a worker is responsible for reporting on. A `queued`
  job is waiting for a dispatcher rather than for a worker, so no amount of age makes it
  stale: an undrained backlog is a fact about the deployment - it shows up as a growing
  `queued` count - and it is not a reason to fail work nobody ever started. The full state
  machine, including what the sweep may and may not touch, is in
  [queue-state-machine.md](queue-state-machine.md).
- Idempotency is structural rather than a flag: the claim is a compare-and-swap,
  `analysis_results` upserts on `(job_id, kind)`, the MIDI key is derived from the job, and
  `queue.complete` refuses a job that has left the state this worker believed it was in. The
  same job run twice writes one set of rows and one object - and the second run is _told_ so,
  which is what the `lost` outcome means.

## Two libraries this could not use, and why

This phase named `librosa`, `essentia` and `basic-pitch`. Two of the three cannot be installed
for this project's Python 3.12 - verified rather than assumed:

- **`essentia`** publishes no Windows build at all (its classifiers are macOS and POSIX), and
  its current release ships only a `cp314` wheel: `uv add essentia` fails with _"only has
  wheels with the following Python implementation tag: cp314"_. Key detection is therefore
  Krumhansl-Schmuckler over `librosa.feature.chroma_cqt`, which is the reference
  implementation essentia's EDMA profiles are an improvement on. `analysis.detect_key` is the
  seam it would slot into.
- **`basic-pitch`** requires `tensorflow>=2.4.1,<2.15.1` on every non-macOS platform, and no
  version in that range has a wheel for 3.12, so the resolver refuses the project outright
  (_"your project's requirements are unsatisfiable"_). Forcing it in with `--no-deps` plus
  `onnxruntime` aborts the interpreter on import. `midi.transcribe_with_pyin` is what runs
  instead, and it is the seam a real transcriber slots into - the pipeline only ever calls it.

Neither is a missing capability so much as a missing dependency, and both are one function away
from being replaced.

## The bucket has to allow `audio/midi`

A storage policy is enforced on every PUT, including the ones the API never performs. The
worker writes its MIDI artifact into the same bucket the browser uploads to, so a bucket
created with `allowed_mime_types = {audio/mpeg, audio/wav}` answers **415** on the worker's
write. The end-to-end test found this the hard way; the fix is in
[upload-flow.md](upload-flow.md) (add `audio/midi`), and the failure now surfaces as
`storage_rejected` on the job instead of as three rounds of `storage_unavailable`.

## Known limitations

- **The MIDI is a monophonic sketch**, not a transcription of a mix. pYIN tracks the
  fundamental of whatever is loudest; polyphony needs a model (see basic-pitch above).
- **The window is the intro.** A song whose material starts later gets a MIDI file that does
  not describe it, and the summary says which window was used.
- **The chords are a reading, not a chart.** A frame of chroma is matched against chord
  templates, so the detector knows nothing about voicing, about inversions outside the chord's
  own tones, or about any extended harmony beyond the ten qualities in
  `chord_templates.py`. A passing tone or a busy arrangement blurs a frame - which is why an
  unsure extension is reported as its triad, and why the confidence travels with every segment
  instead of being hidden.
- **A slash bass is the lowest strong bin of C2-C4**, a register a kick drum also occupies. The
  note is only claimed when it is one of the chord's own tones and the segment is clear enough
  (`SLASH_CONFIDENCE`), which removes most of the ways it can be wrong and not all of them.
- **The timeline is frame-accurate, not bar-aligned.** It says what is played, not which bar it
  is played in; snapping is deferred, and the grid it would use is already computed.
- **The budget is checked between stages**, because nothing portable can interrupt a detector
  that is already running (there is no `SIGALRM` on Windows). A single pathological file can
  still overrun before it is noticed.
- **A `lost` job can leave an object behind.** If the MIDI was already written and the job had
  been reaped, that object stays in the bucket unreferenced. Asking whether the job is still
  ours _before_ storing anything would be a race; the guarded write is the truthful check, and
  the key is derived from the job, so a re-run overwrites the same object.
- **The recording is downloaded whole** (up to the 200 MiB upload cap) and written to a temp
  file, because that is what the decoders take. Streaming is the fix if that ever matters.
- **`--once` is the deployment story for now.** There is no RunPod dispatch, no per-user
  concurrency limit and no dead-letter queue; the RunPod client is the next phase.

## Tests

```bash
$env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
uv run --directory apps/api --group worker pytest
```

| Suite                              | Needs                                | Covers                                              |
| ---------------------------------- | ------------------------------------ | --------------------------------------------------- |
| `test_worker_pipeline.py`          | a database                           | claim, write, the success path, idempotency         |
| `test_worker_pipeline_failures.py` | a database                           | every failure code, and `lost`                      |
| `test_worker_artifacts.py`         | nothing                              | key shape, digests, the object trio                 |
| `test_worker_runner.py`            | nothing                              | drain-once, the job cap, the idle wait, the sweep   |
| `test_worker_heartbeat.py`         | a database                           | the thread, and what it does when the job is gone   |
| `test_worker_analysis.py`          | the audio group                      | 120 BPM click, A minor and C major, silence refused |
| `test_worker_chords.py`            | the audio group                      | the four triads of a loop, an inversion, silence, the grammar |
| `test_worker_midi.py`              | the audio group                      | a real SMF, the triad that was played, the window   |
| `test_song_chords.py`              | a database                           | the timeline, its digest, and every refusal         |
| `test_worker_e2e.py`               | a database, a bucket, `MYBAND_E2E=1` | the whole path: presigned PUT to rows               |

The audio suites skip themselves when the `worker` group is not installed and the database
suites when `MYBAND_TEST_DATABASE_URL` is unset, the same convention the rest of the suite
uses. `test_worker_e2e.py` is gated separately because it is the slow one, and because it needs
the local stack's bucket.
