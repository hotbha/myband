# Release readiness

What is in the next release, what is knowingly not, what has to be true before anyone outside the
team touches it, and how to take it back if it goes wrong. It is a companion to
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) rather than a replacement: that file is the
standing risk register (`R1`-`R10`) and the public-beta gates; this one is the state of **one
release candidate** and the plan for a **closed beta of ten people**.

**Status: ready to merge. B1-B5 are closed as of 2026-10-11 - each has a _Closed_ line in section 3;
B1 and B2 rest on [BETA_SIGNOFF.md](BETA_SIGNOFF.md), which also carries the launch decision, and
B3-B5 on [BETA_READY.md](BETA_READY.md). Not ready for a public beta.**
Feature development stops here: no new capability is added on this branch after the cut.

## What is being released

|                  |                                                                                                                                                                                                                                                    |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Branch           | `feat/music-analysis-v2`, three commits over `main` (`4428e2d`)                                                                                                                                                                                    |
| Head             | `8bf2d88` - chord UX over `1e32e71` (the pYIN fix) over `d8c51bf` (chords)                                                                                                                                                                         |
| Diff             | 32 files, +3012 / -156; **no migration**, so no schema change and no database rollback. The uncommitted release-prep change on top of it stages 12 paths - see [BETA_READY.md](BETA_READY.md)                                                      |
| Pipeline version | `MYBAND_PIPELINE_VERSION=0.2.0` - B5 is closed; see [BETA_READY.md](BETA_READY.md)                                                                                                                                                                 |
| Verified green   | `pnpm test:api` **248 passed / 0 skipped / 0 failed in 15.79 s** against a migrated database - B1; `ruff check` clean, `pnpm lint`, `pnpm typecheck` and `pnpm build` exit 0 as recorded in [BETA_READY.md](BETA_READY.md)                         |
| Verified on      | Windows development box, `MYBAND_ENV=development`, real recordings - through the browser for B2: sign-up, sign-in, three uploads, the worker, the chord UI and three MIDI downloads, all in [BETA_SIGNOFF.md](BETA_SIGNOFF.md) - not on the RunPod |
| Not verified     | Cloudflare R2, a deployed Supabase, the RunPod path, Google sign-in, a human ear on the chords and the notes, and any failure path induced through the browser - the list is [BETA_SIGNOFF.md](BETA_SIGNOFF.md), section 9                         |

The verification commands, and the note that the database cases skip themselves, are in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md#commands-this-rests-on).

## 1. Features complete

| Area                   | What works                                                                                                                                                                                                                                                                             | How it is verified                                                                                           |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Auth                   | Google and email sign-in, session held by Supabase, `/dashboard` and `/songs/[id]` protected twice - middleware, then `requireIdentity` as the real boundary (`features/auth/session.ts`)                                                                                              | `tests/test_api_routes.py` (database-gated), manual checklist                                                |
| Upload                 | Browser PUTs straight to R2 against a presigned URL; `.mp3` and `.wav` accepted, other types and anything over 200 MiB refused in the browser with no request; `uploads.expires_at` shares the URL's clock                                                                             | `tests/test_upload_flow.py` (database-gated), manual checklist                                               |
| Queue                  | `claim_next` (`FOR UPDATE SKIP LOCKED`), `begin`, `complete` and `fail` with compare-and-swap guards, `reap_stale` sweep; statuses `queued`, `dispatched`, `running`, `succeeded`, `failed`                                                                                            | `tests/test_queue.py`, `test_queue_batch.py`, `test_queue_sweep.py` (all database-gated)                     |
| Duration, BPM, key     | Duration from the container header (no decode), tempo from `librosa.beat.beat_track`, key from Krumhansl-Schmuckler over `chroma_cqt` across all 24 keys; stored as columns on `songs`                                                                                                 | `tests/test_worker_*.py`                                                                                     |
| **Chords** (new)       | Whole-song `chroma_cqt` -> templates -> a 121-state Viterbi pass with an explicit no-chord state; grammar of ten qualities over twelve roots plus `/<bass>`; extensions below `EXTENSION_CONFIDENCE` reported as their parent triad; frame-accurate, deliberately not snapped to beats | `tests/test_worker_chords.py` 16/16, `tests/test_song_chords.py` (database-gated), `docs/analysis-worker.md` |
| **Chord screen** (new) | `/songs/[id]`, server-rendered: the timeline, the chords the song is made of, one confidence sentence, a per-view coverage bar, a rests count, and a toggle between **simple** (default) and **as detected**; an empty timeline is a state, not an error                               | Manual checklist - the web app has no test runner (R7)                                                       |
| **MIDI**               | A monophonic pYIN sketch of a bounded window, written to R2 and downloadable as `<title>.mid`; `transition_min_prob` (`1e32e71`) is what let the Viterbi decode leave the unvoiced state, which is the fix this release was opened for                                                 | `tests/test_worker_midi.py` 7/7, `tests/test_midi_download.py` (database-gated)                              |
| Operations             | `GET /admin/metrics` - queue counts by status, in-flight, oldest age per state, finished/failed/reaped recently, library totals - behind `MYBAND_METRICS_TOKEN`, and absent (404) on a deployment that never set one                                                                   | `tests/test_admin_metrics.py` (database-gated)                                                               |

**Validated on real recordings, not fixtures.** Three commercial recordings were taken through the
worker's own stage functions and the shipped chord reader end to end, and all three produced BPM,
key, chords and MIDI, with none empty. The chord screen's reason for existing showed up in the
numbers: on one recording the _as detected_ coverage is 0.589 and the _simple_ reading is 0.916, and
on another 0.614 -> 0.877 - the default view describes the song, the detected view is the detector's
honest opinion. Both are one tap apart, which is the whole point of the toggle.

Nothing above claims song sections. They are the next analysis stage and are not in this release.

## 2. Known limitations

Accepted, measured, and written down rather than discovered by a beta user.

**The MIDI covers only the first 30 seconds of a recording.** `MYBAND_WORKER_MIDI_WINDOW_SECONDS`
defaults to 30 (`ge=5, le=600`), because the pitch tracker costs roughly a second per second of
audio and the window is what keeps a long song's job bounded. A window sweep on the three
recordings (30 s / 60 s / 120 s / whole song) measured what the cap costs: a whole-song
transcription is **2x to ~11x** more MuseScore-visible notes than the first 30 seconds, at a peak of
232 MiB on a 345 s song - against `analyze` peaking at 642 MiB on the same song, so MIDI is not the
memory outlier - and 11-19x realtime, at most 31 s for a 5:45 song inside a 900 s budget. The
recommendation is a bounded whole-song transcription (or a 120 s elbow); **it is not implemented
here**, and a whole song longer than ten minutes is not expressible at all without raising the
field's `le=600`. Whoever implements it should re-measure on the RunPod CPU profile, since these
numbers come from a Windows box.

**Deliberate algorithm choices.** Chords are read from the audio rather than from the MIDI (the
sketch is monophonic, follows the bass, and cannot carry harmony); segments are frame-accurate with
no beat or bar snapping; confidence is one sentence under the card rather than a meter per row;
the wide grammar is kept in storage so a later feature never has to rewrite a timeline already
written. Each of those is argued where it lives, in [docs/analysis-worker.md](docs/analysis-worker.md).

**Smaller, known, accepted.**

- `apps/web/features/uploads/components/chord-timeline.tsx` is 303 lines, just over the 300-line
  rule. Reviewed and left as it is rather than split for the number's sake.
- `docs/midi-transcription-options.md` is **untracked** and its explanation of empty MIDI files is
  now stale - it blames `switch_prob` and voicing, when the cause was `transition_min_prob`. Decide
  its fate before the cut: correct it and commit it, or delete it.
- `pnpm format:check` fails on **7 tracked files** now, down from 41 - B3 put `spike/` in
  `.prettierignore`, and the 34 that disappeared are exactly the `spike/` tree. Whether they failed
  before the branch touched them **was** established on 2026-10-11, by formatting each `main`
  (`4428e2d`) blob with prettier and comparing the bytes, and it is not one answer:
  `docs/upload-flow.md` and `docs/queue-state-machine.md` already failed on `main`;
  `README.md`, `PRODUCTION_READINESS.md` and `docs/analysis-worker.md` were clean on `main` and were
  made offenders by this branch's own doc edits, so they are the only prettier debt the release
  creates; and `features/uploads/jobs.ts` and
  `features/uploads/components/library-refresh.tsx` are clean as stored and fail only in this
  worktree, whose CRLF predates `.gitattributes` arriving. Treat it as a chore commit of its own -
  never as part of the release commit.
- No cancel path, no retry route, no quota or rate limit, no GPU dispatcher: `canceled` is a status
  nothing produces, a failed song can only be re-uploaded as a new song, and a worker is a process
  someone runs. These are R3, R5 and the dispatcher entry in the register, not new gaps.
- The API's own `where user_id = %s` scoping is the only thing between two accounts, because it
  connects as the `postgres` role and bypasses RLS (R1). One ownership check per route, and
  `song_not_found` for someone else's, a deleted or an unknown id alike.

## 3. Launch blockers

Five, all measured, ordered by what they would cost. B1-B3 were the merge gates for this release and
B4 and B5 the gates before it is pointed at anyone outside the team; **all five are closed as of
2026-10-11**. A closed blocker keeps its letter and gains a _Closed_ line - the measurements behind
B3-B5 are in [BETA_READY.md](BETA_READY.md), and behind B1 and B2 in
[BETA_SIGNOFF.md](BETA_SIGNOFF.md), which is also where the launch decision and the recommended first
cohort live.

**B1 - 114 of 247 tests did not run, and they are the database ones.** `pnpm test:api` reports 133
passed and 114 skipped, every skip being `set MYBAND_TEST_DATABASE_URL to test against a migrated
database`: `test_rls.py`, `test_schema.py`, `test_queue*.py`, `test_api_routes.py`,
`test_admin_metrics.py`, `test_midi_download.py`, `test_upload_flow.py`,
`test_worker_pipeline*.py`, and - the one that belongs to this release - all ten cases of
`test_song_chords.py`, including the ownership assertions that stand in for R1. No row-level
security, ownership-404 or schema property in this release has been executed against a real
database. **Close:** point `MYBAND_TEST_DATABASE_URL` at a migrated Postgres and get to 0 skips
(see the commands in the register).

**Closed 2026-10-11.** Pointed at the local stack's migrated database, the suite reports **248 passed,
0 skipped, 0 failed in 15.79 s** - and the 0 needs **two** variables, not one: `MYBAND_TEST_DATABASE_URL`
alone leaves exactly one skip, because `test_worker_e2e.py` gates itself on `MYBAND_E2E=1` as well.
Everything the blocker listed ran against a real Postgres: the RLS and schema suites, the
ownership-404 assertions, the queue state machine including the case that has to commit, and the
end-to-end upload-to-results path. The suite left the database as it found it, and it was run with
the standalone worker stopped so that no other claimant shared the queue. Evidence, and the amended
command: [BETA_SIGNOFF.md](BETA_SIGNOFF.md).

**B2 - the HTTP path was never exercised.** There is no Supabase session and no test database on
this machine, so the browser-to-R2 upload, the queue hand-off, the worker claiming a real row and
the chord download over HTTP were never run. The pipeline itself was validated on real recordings
by calling the shipped stage functions and the shipped chord reader directly, which covers the
analysis and the contract but not the wiring between them. **Close:** `pnpm dev` and
`pnpm worker:api` together, upload the three recordings through the browser, and open each song
page.

**Closed 2026-10-11.** All four steps ran through the product's own screens against the shipped API:
an account created and signed in through `/login`, the three recordings uploaded from the browser
(3 x `POST /uploads/presign` 201 and 3 x `POST /uploads/complete` 201), the worker claiming and
analysing each real job (3 x `job succeeded`, no failure), the chord timeline read on each song page
including the Simple / As detected toggle, and all three MIDI files downloaded through the button
(3 x `GET /songs/{id}/midi` 200). Across the whole run the API answered 40 x 200 and 6 x 201 and
nothing else - no 4xx, no 5xx, no traceback - and **Tera Suroor, the recording that motivated this
release, went from an empty 66-byte tempo map to 29 notes over 269 bytes.** Evidence:
[BETA_SIGNOFF.md](BETA_SIGNOFF.md).

**B3 - `spike/` is untracked and _not ignored_ on this branch, so the cut can swallow 776 MB.**
`spike/` holds 12,807 files / 775.9 MB (6,902 files / 408.3 MB excluding `.venv-managed` and
`vendor/`). Neither `.gitignore` nor `.prettierignore` on this branch excludes it - only
`spike/basic-pitch-onnx/.gitignore`, itself untracked, keeps a casual `git status` quiet - and
`git check-ignore spike` reports _not ignored_. A `git add -A` at release time stages the whole
thing. The same drift is why switching to a non-spike branch deletes the tracked `.gitignore` and
`.prettierignore` (they exist in `ed056c1`, on `spike/basic-pitch-onnx`), which is how this was
found. **Close:** cut the release from a clean clone, or add `spike/` to both ignore files and
commit that before the release commit.

**Closed 2026-10-11.** The ignore-file route was taken: `spike/` is in both `.gitignore` and
`.prettierignore`, so `git check-ignore -v spike` reports `.gitignore:44:spike/` and
`git add -A --dry-run` stages 12 paths with none under `spike/`. The same change dropped
`pnpm format:check` from 41 failing files to 7. Measurements, and the list of what a commit would
actually take: [BETA_READY.md](BETA_READY.md). The entries still have to be committed before the
release commit - see the cut checklist.

**B4 - a production boot demands RunPod credentials that nothing reads.**
`Settings._require_production_secrets` fails closed unless `RUNPOD_API_KEY` and
`RUNPOD_ENDPOINT_ID` are set when `MYBAND_ENV=production`, but no module calls RunPod: a search
finds only the settings themselves, the `analysis_jobs.runpod_job_id` column and a
`queue.dispatch` parameter with no caller. A deployment is therefore asked for secrets for a
component that does not exist yet, and can only satisfy the check by supplying real values early or
plausible-looking placeholders. **Close:** set the values you will need next sprint, or relax the
validator until the dispatcher lands - either way, decide it deliberately rather than at 1am.

**Closed 2026-10-11.** Decided deliberately: the validator now demands exactly the five settings the
running code reads, and a test pins both halves - one asserts a production boot names the missing R2
key and does _not_ name RunPod, the other asserts a boot succeeds with both RunPod fields empty
(`tests/test_config.py`; the second is what took the suite from 133 to 134 passing). Verified live as
well: a production boot with those two empty succeeds, and one with `R2_SECRET_ACCESS_KEY` missing is
still refused and names it. The dispatcher's commit is what adds the demand back.

**B5 - two docs and one setting still describe the pre-chords world.** `README.md` ("Not implemented
yet") and `PRODUCTION_READINESS.md` ("Deliberate gaps, accepted for beta") both say chords and song
sections have no stage and no screen, which this release makes false for chords - and the register
is the document support is told to trust. Separately, `MYBAND_PIPELINE_VERSION` is still `0.1.0`
even though the worker's output changed (a chords artifact and the stage that produces it), and the
setting's own comment says to bump it whenever the output shape changes. **Close:** update both
docs, and bump the version deliberately - it is stamped on every job row and is what makes a stored
result interpretable after the pipeline moves.

**Closed 2026-10-11.** Both docs now describe chords as shipped, `docs/upload-flow.md` and
`apps/api/README.md` with them, and the config default and `.env.example` both read `0.2.0`. One
thing the check exposed: the default is only a default - `apps/api/.env` is untracked and still
pinned `0.1.0`, so the running application kept reporting `0.1.0` while every tracked file said
`0.2.0`. It was corrected on this machine, but **any other machine or deployment still pinning
`0.1.0` has to be moved, and the API and the worker together** - which is why the checklist line
below is about the deployment and not about the repository. Evidence: [BETA_READY.md](BETA_READY.md).

**Inherited gates.** Everything in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) above still
stands and this release does not close any of it. The ones that will bite a beta specifically: a
worker has to be alive or a job is never reaped (R2), nothing retries a failed job automatically
(R3), nothing in the bucket is ever deleted and uploads are unbounded (R4, R5), and no restore has
been rehearsed (R10).

## 4. Beta launch checklist

Each line is a thing to do and see, not a thing to believe. B1-B5 are the blockers; the rest are the
register's gates, restated for this release.

**The cut**

- [ ] B3: commit the prep change that puts `spike/` in both ignore files (this replaces the
      clean-clone route), then confirm `git diff --cached --name-only` lists no path under `spike/`,
      no `.venv`, no `vendor/` - and decide the fate of the untracked, unignored
      `docs/midi-transcription-options.md`, which a `git add -A` would otherwise take
- [ ] B5: the docs describe chords as shipped and `MYBAND_PIPELINE_VERSION` is bumped in the
      repository; **check the deployment agrees on `0.2.0` and that the worker and the API were moved
      together** - a stale `.env` or platform value silently wins over the new default
- [ ] `docs/midi-transcription-options.md` either corrected and committed, or deleted
- [ ] The prettier chore (and any line-ending fix) is its own commit, before the cut, never inside it
- [ ] Freeze: no feature commits after the tag

**Verification**

- [x] B1: `MYBAND_TEST_DATABASE_URL` **and `MYBAND_E2E=1`** set, `pnpm test:api` reports **0 skipped**,
      248 passed (2026-10-11, [BETA_SIGNOFF.md](BETA_SIGNOFF.md))
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm build` all exit 0 on the cut commit
- [ ] `pnpm lint:api` (ruff) and `ruff format --check` clean
- [ ] B2: the smoke test below, on the deployed stack rather than locally

**Configuration**

- [ ] `MYBAND_ENV=production` (this is what switches the interactive docs off), `MYBAND_LOG_LEVEL=info`
- [ ] `MYBAND_CORS_ORIGINS` names the deployed web origin and nothing else - no wildcard
- [ ] `MYBAND_METRICS_TOKEN` set; `/admin/metrics` answers counts with it and `401` without, and
      `404` from anywhere that is not the deployment (B4's decision is also made here)
- [ ] `MYBAND_WORKER_JOB_TIMEOUT_SECONDS` and the TTLs revisited for the deployed profile, not the
      development defaults

**Storage**

- [ ] The bucket exists with the CORS and content-type settings in
      [upload-flow.md](docs/upload-flow.md) - `audio/midi` for the download and `application/json`
      for the chords artifact both included
- [ ] An R2 lifecycle rule covers stray objects (R4, R5)
- [ ] R2 credentials are scoped to this bucket, and rotating them is a documented step

**Database**

- [ ] Migrations applied with the CLI (`supabase db push`), never through the dashboard SQL editor -
      this release adds none, so this is a check rather than a step
- [ ] `auto_expose_new_tables = false` on the cloud project, as it is locally
- [ ] One restore rehearsed, and the person who would do it at 2am knows where this file is (R10)

**Auth**

- [ ] Google provider configured, with `https://<project-ref>.supabase.co/auth/v1/callback`
      registered in Google
- [ ] Site URL and redirect URLs list the production origin
- [ ] SMTP configured, "Confirm email" decided, one sign-up read end to end in a real inbox (R9)

**Queue and workers**

- [ ] At least one worker is running with the audio dependency group installed, and it is restarted
      if it dies (R2)
- [ ] A killed worker's job is reaped: `reaped_recently` moves and the row shows `failed` with
      `error_code = 'stale'`
- [ ] Alerts exist on `oldest_in_flight_seconds` and on `failed_recently` (R2)

**Smoke test, on the deployed stack**

- [ ] An MP3 uploads: the bar reaches 100%, the row appears, the badge moves Queued -> Starting ->
      Analysing -> Analysed without a refresh
- [ ] The song page opens from the library row and shows a timeline with a coverage bar
- [ ] The **as detected** toggle reveals labels the simple view was hiding, and a differing row says
      so on the row itself
- [ ] A percussion or spoken-word track shows "no chords in it at all" as a state, not an error
- [ ] MIDI downloads as `<title>.mid` and opens in MuseScore
- [ ] A song whose job has not succeeded shows no MIDI button and an "analysis has not been
      produced yet" sentence rather than an error
- [ ] `/dashboard` with the API stopped still renders the uploader and says the library could not be
      loaded

**Support and comms, before the first invite**

- [ ] A user can reach a human from the product or from the confirmation email
- [ ] Whoever answers has `/admin/metrics`, the queries in
      [queue-state-machine.md](docs/queue-state-machine.md), the failure codes in
      [docs/analysis-worker.md](docs/analysis-worker.md), and this file
- [ ] Beta users are told the two things that will otherwise read as bugs: the MIDI is the first 30
      seconds, and the default chord view is deliberately simpler than what was detected

## 5. Ten-user validation plan

A closed beta of ten, recruited by hand, run for two weeks after the smoke test passes. The point is
not load and not billing - it is whether the two things this release is about, a chord timeline and
a MIDI sketch, are useful to people who play, and whether the screens explain themselves without us
in the room.

**Who, and why that mix.** Four who play an instrument and want to play along (the chord screen's
reason for existing), three who produce or arrange (they will judge the MIDI and want the key), two
who sing or perform over a track (they care about key and sections, which are absent - a useful
disappointment to hear early), and one who is not a musician at all, as the control for whether the
screen explains itself. Each brings their own recordings; each is also given the same three
recordings, whose chords were measured in this release - detected coverage 0.589 against a simple
reading of 0.916, and 0.614 against 0.877 - so that "the chords are wrong" can be checked against
the detector's own numbers instead of an impression.

**The session, once per participant, 20-25 minutes, observed or screen-shared.**

1. Sign up and upload one recording, unaided. Nothing about the flow is explained first.
2. Say what they hear - tempo and key - before looking at the screen, then compare.
3. Find the chords and play along. Record how long it takes to reach the song page unaided.
4. Switch to **as detected**, then say which reading they would use and why.
5. Download the MIDI, open it in whatever they use, and say what is missing from it.
6. Report the one thing that was wrong, in their own words.

**What we are trying to learn, per step.** Steps 1-3 measure whether the library-to-song navigation
works at all; step 4 is the release's central design bet (is _simple_ the right default, or is hiding
the detected label a mistake?); step 5 answers the one question only a user can - whether a
30-second monophonic sketch is worth more than nothing, which is the whole argument for the window
and the thing that decides the next piece of work; step 6 is what fills the next register entry.

**Pass, and stop.** Pass: 8 of 10 upload unaided; 7 of 10 reach the song page unaided; median time
to first chord under two minutes; at least 6 prefer the simple reading _and_ can say what the
detected one added; at least 3 open the MIDI somewhere real; no failure reaches a user without a
sentence they understand. Stop and fix before continuing: 3 or more users who cannot find the chord
page means navigation, not analysis, is the problem; the empty-chords state appearing on tonal
material is a bug rather than a preference; any question that needs the failure codes means the
screen is not carrying its own weight.

**Housekeeping.** Participants are asked to upload only material they have the rights to, and their
library is removed by hand on request - there is no delete route or bucket drainer yet (R4), so this
is a manual step someone must own. Not in this round: billing, sharing, song sections, MIDI beyond
the window, and anything needing a GPU.

## 6. Analytics to track

**What exists today, and it is less than it looks.** `GET /admin/metrics` reports queue counts by
status, `in_flight`, `oldest_queued_seconds`, `oldest_in_flight_seconds`, `finished_recently`,
`failed_recently`, `reaped_recently` and library totals (`songs`, `song_owners`) over a window - a
deliberately impersonal payload. The worker logs one structured line per job carrying `job_id`,
`song_id`, `seconds`, `bpm`, `musical_key`, `notes`, `chords`, `beats`, and every failed job keeps an
`error_code` from a stable set (`app/workers/errors.py`). There is **no product analytics, no
per-stage timing, and no queryable join from a person to their results** - `library.song_owners` is
the closest thing to a per-user count, and `seconds` exists only as a log line.

| What to track                            | Where it comes from today                                             | What has to be added                                                                                                                                                                                               |
| ---------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Queue depth and lag                      | `/admin/metrics`: `oldest_queued_seconds`, `oldest_in_flight_seconds` | Nothing - alert on the ages rising, per R2                                                                                                                                                                         |
| Failure rate, and which code             | `failed_recently`, plus `error_code` per job                          | Group the log lines, or read `analysis_jobs` directly; the codes are already stable                                                                                                                                |
| Job duration, per stage                  | `seconds` on the done/failed line, for the whole job                  | Stage timings: `Produced` carries none, so nobody can say today whether pYIN or chords spent the budget. pYIN separately - it is what the window exists for                                                        |
| Uploads per day, and abandon rate        | Nothing                                                               | A count of `uploads` against `songs`; today it is a manual query                                                                                                                                                   |
| Time to first chord                      | Nothing                                                               | Job completion minus upload creation; both are already columns                                                                                                                                                     |
| Chord screen visits, and the toggle rate | Nothing                                                               | A counter on the page and on the toggle - the toggle rate is the direct measure of whether _simple_ is the right default (step 4 of section 5)                                                                     |
| **Coverage, simple versus detected**     | Only inside each `chords.json` artifact in R2                         | The single most useful quality number, and the one this release's measurement was about. Copy the summary onto `analysis_results` or compute it on read - as it stands, answering it means fetching every artifact |
| Empty-chord rate                         | Nothing                                                               | The same summary: how often a recording yields no chords at all                                                                                                                                                    |
| Repeat use                               | Nothing                                                               | Second uploads per account within 7 days - the beta's real success metric                                                                                                                                          |
| Quality attribution                      | `pipeline_version` is stamped on every job row                        | Put it on every metric emitted, so a change in chord quality is attributable to a release rather than to a hunch                                                                                                   |

Two rules for whatever gets added: **the operator payload stays counts and ages, never a title or an
email** - that property is why `/admin/metrics` can be handed to whoever is on call - and product
analytics stays counts plus ids for the same reason. `pipeline_version` goes on every event.

## 7. Rollback plan

**This release is cheap to take back, and that is a property of its shape rather than of luck.** It
is additive and it carries no migration. What changed: a chord stage and a `chords.json` artifact in
the worker, the pYIN fix in `midi.py`, one new API route (`GET /songs/{id}/chords`), one new page
(`/songs/[id]`), and additive changes to the library list and the shared types. What did not change:
the schema (four migrations, untouched), the queue's state machine, the auth path and the upload
path. Nothing in the database needs un-applying, and every artifact already written stays valid.

**Roll back in this order: worker, then API, then web.** The worker is what writes the new artifact,
so stopping it ends the bleeding and is reversible by itself; the API answers a superset of what it
used to (an older web build simply never asks for chords); the web is what expects the new API, so
it goes last.

| Layer    | What rolling back means                               | What a user sees                                                                                                                                                            |
| -------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Worker   | Stop it, redeploy the previous revision               | Chords written before the rollback stay; songs analysed after it get none, and their song page shows the not-ready sentence indefinitely                                    |
| API      | Redeploy the previous revision                        | The chords route disappears; the song page shows its error notice rather than crashing, because any error other than `analysis_not_ready` is already rendered as a sentence |
| Web      | Redeploy the previous build                           | `/songs/[id]` disappears and the dashboard is library-only again; the library rows and upload flow are unaffected                                                           |
| Database | Nothing to do - no migration in this release          | Nothing. If a migration did land inside the bad window, add a new one rather than editing history (`README.md`)                                                             |
| Bucket   | Nothing to undo; unreferenced objects are the R4 case | Nothing. An R2 lifecycle rule is the backstop                                                                                                                               |

**Idempotency is what makes a re-run safe.** `analysis_results` upserts on `(job_id, kind)`, the MIDI
object key is derived from the job, and `queue.complete` refuses a job that has left the state the
worker believed it was in - so re-running a song with a fixed worker overwrites one set of rows and
one object rather than duplicating them.

**What makes us roll back.** Stop the worker first on any of these, and decide about the rest
afterwards:

- any read of another account's data (an R1-shaped leak, however small)
- `internal_error` at any rate at all - that code means a bug, not a bad recording
- `failed_recently` climbing with one dominant `error_code`
- the empty-chords state appearing on tonal material
- p95 job `seconds` approaching the 900 s budget
- the song page erroring instead of showing its not-ready sentence - a contract break rather than a
  data problem

**Jobs caught in flight.** A stopped worker leaves its job `running` and nothing fails it until a
worker runs the sweep, which is exactly R2's shape - so restart the _previous_ worker and let the
sweep reap it; the job ends `failed` with `error_code = 'stale'`. The user is asked to re-upload,
because there is no retry route (R3). That is the rollback's one real cost: a long bad window means
a backlog of re-uploads, which is one message to the ten users rather than ten messages.

**Cost and ownership.** Under half an hour, and a redeploy rather than a rebuild: keep the previous
web build, API image and worker revision tagged for the whole beta. Whoever is on call stops the
worker on their own judgement, because it is the reversible action and needs no ceremony; rolling
back the API and the web is a decision for the two people who own the deploy, made together, with
this file open. Afterwards the failure gets a numbered entry in the register, this file is re-read
at the next milestone, and nothing is fixed forward during the incident itself.

## How this file is maintained

- It describes **one release**, where [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) describes
  the platform. When this release is out and the ten users are through it, replace sections 1-5 with
  the next release rather than letting this become a second register - the standing risks belong in
  the register and nowhere else.
- Blockers are lettered (`B1`...`B5`) and keep their letter until they are closed; a closed blocker
  gains a _Closed_ line saying what closed it and when. Same rule as the register's numbered risks,
  for the same reason: commits, tickets and messages cite these.
- Every claim carries its evidence - a command, a file, a measurement - or says plainly that it was
  not established. A limitation with no number beside it is a guess, and a guess does not belong in
  a document that decides whether software ships.
- Re-read it at the cut, at each deploy of this release, and before the first invite goes out.
