# Beta sign-off

The gate this file answers is the one [RELEASE_READY.md](RELEASE_READY.md) left open: **B1** (every
database-backed test skipped itself) and **B2** (the HTTP path was never exercised). Both were closed
on **2026-10-11** the only way a launch blocker can be closed - by running the release the way a user
runs it, and by running the suites the way they were meant to run - and this file is the measurement
behind both closures plus the list of what the run did **not** settle.

**Status: B1 and B2 closed. Launch: yes - a closed beta of ten people, on the conditions in section 6.
Not a public beta.** Blocker lines live in [RELEASE_READY.md](RELEASE_READY.md) (section 3), standing
risks in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); this file is the evidence.

## 1. What was run

|            |                                                                                                                                                         |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Code       | `8bf2d88` on `feat/music-analysis-v2` (chord UX over the pYIN fix over chords), plus the uncommitted release-prep change                                |
| When       | 2026-10-10 23:37-23:47 UTC, one sitting; the same Windows 11 development box as the rest of the evidence, CPU only                                      |
| Database   | local Supabase, all four migrations applied: `core_schema`, `functions_and_triggers`, `rls_and_grants`, `song_analysis_summary`, six tables in `public` |
| Services   | `pnpm dev` (API `127.0.0.1:8000`, web `localhost:3000`) and `pnpm worker:api` - logs to `%TEMP%\myband-beta\{dev,worker}.log`, outside the repository   |
| Tester     | a dedicated account created through the sign-up form, `beta.tester@myband.local`, so its library holds only this run's songs                            |
| Recordings | `spike/basic-pitch-onnx/audio/`: `jyoti.mp3`, `himesh-reshammiya-tera-suroor-mp3-pm.mp3`, `ganesha-kartikeya-race-short-audio.mp3`                      |
| Storage    | the local stack's S3 endpoint behind the `myband-audio` bucket - **not** Cloudflare R2, which this run never touched                                    |
| MuseScore  | MuseScore Studio **4.7.5** (build 260831071), `X:\Program Files\bin\MuseScore4.exe`                                                                     |

## 2. B1 - the database suites

**Closed: 248 passed, 0 skipped, 0 failed in 15.79 s.**

Before this run the report was 134 passed / 114 skipped, and every skip carried the same sentence:
`set MYBAND_TEST_DATABASE_URL to test against a migrated database`. The stack had been up for two
days; nothing had ever pointed the suite at it.

```powershell
$env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
$env:MYBAND_E2E = "1"
pnpm test:api
```

**Two variables, not one - and that is the finding.** `MYBAND_TEST_DATABASE_URL` alone takes the
suite from 114 skips to **1**: `tests/test_worker_e2e.py` gates itself on `MYBAND_E2E=1` as well. So
the checklist's "0 skipped" needs both, and the amended line is worth writing down rather than
leaving as a surprise on the next machine. The command in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) is still right for the register; this is the extra
variable the cut has to set.

What 114 skips turning into 114 passes bought, in the terms the blocker was written in:

- `test_rls.py`, `test_schema.py`, and the ownership-404 assertions in `test_api_routes.py`,
  `test_midi_download.py` and `test_song_chords.py` ran against a real Postgres with the real
  policies - the cases that stand in for R1, which had never executed against a database.
- The queue state machine ran for real (`test_queue.py`, `test_queue_batch.py`,
  `test_queue_sweep.py`), including the two-competing-dispatchers case, which is the one test that
  has to commit.
- `test_worker_e2e.py` ran the whole path in one test: a presigned PUT over HTTP, a completed upload,
  a queued job, the shipped pipeline, and the results read back from the database. It is the part of
  section 3 that runs without a browser.

Three things worth recording about how it was run:

- **The standalone worker was stopped for the suite, and restarted after.** It polls the same queue
  every five seconds (`MYBAND_WORKER_POLL_SECONDS`), and a live worker can claim a job a test is
  about to claim itself - which would have made the run flaky, and a flaky gate is worse than a slow
  one.
- **The database was left exactly as it was.** After the suite: three `uploads` rows, three `songs`,
  three `analysis_jobs`, twelve `analysis_results` - this run's three songs and nothing else - and
  `auth.users` still holding two rows. The `conn` fixture rolls its transaction back and the one test
  that commits cleans up after itself, which is why the assertion above is a measurement and not a
  hope.
- **No environment leaked in.** The persistent shell's stale `MYBAND_*` exports that produced
  fourteen spurious failures earlier in this release were checked for and cleared before the run
  (`Get-ChildItem Env:` reported no `MYBAND_`/`R2_` variable other than the one the run sets).

## 3. B2 - the HTTP path

**Closed: signed up, signed in, uploaded three recordings, watched all three to success, read the
chords on the song pages, and downloaded all three MIDI files - every step through the shipped
screens against the shipped API.**

| Step             | What happened                                                                                                                      | Evidence                                                                                                                                                                                       |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sign up          | `beta.tester@myband.local` created through the form on `/login` (local email confirmations are off)                                | landed on `/dashboard`; "Signed in as beta.tester@myband.local"; library read "Nothing here yet."                                                                                              |
| Sign in          | logged out, then signed back in with the same credentials                                                                          | `/login` -> `/dashboard`, same identity                                                                                                                                                        |
| Upload           | three files, one at a time, through choose-file-then-Analyse                                                                       | 3 x `POST /uploads/presign` **201**, 3 x `POST /uploads/complete` **201**; each answered "<name> is queued for analysis." with status `queued`, pipeline `0.2.0`                               |
| Queue, worker    | the worker claimed each job and analysed it                                                                                        | 3 x `job succeeded` in the worker log, 0 x `job failed`, no `error_code`                                                                                                                       |
| BPM, key, chords | three artifacts stored per song, read back from `analysis_results`                                                                 | section 4                                                                                                                                                                                      |
| Chord UI         | `/songs/{id}` rendered the timeline for all three: vocabulary, coverage, per-chord confidence, and the Simple / As detected toggle | Jyoti: _Simple_ shows D, Dm, Am, Edim, A over 92% of the recording; _As detected_ shows Dsus2, Dm7, Am7, Edim/G over 59%, and "Made of" moves from `D G C Gm Dm A#` to `C D G Gm Gmaj7 A#maj7` |
| MIDI download    | the MIDI button asked the API for a link, the bucket answered                                                                      | 3 x `GET /songs/{id}/midi` **200**; the browser saved `jyoti.mid`, `himesh-reshammiya-tera-suroor-mp3-pm.mid`, `ganesha-kartikeya-race-short-audio.mid`                                        |
| Library          | the dashboard listed exactly the three songs, all badged "Analysed", each with a MIDI button                                       | 3 rows: `108 BPM · C# minor · 1:02`, `117 BPM · C# minor · 5:45`, `89 BPM · G major · 4:07`                                                                                                    |

Across the whole run the API answered **40 x 200 and 6 x 201 and nothing else**: no 4xx, no 5xx, no
traceback in either log. Uploads queued in under a second each; the worker took 40 s of wall clock
for all three songs including its 5 s poll.

Two cosmetic things this run surfaced. Neither is a blocker and neither is fixed here:

- **`Job 01a12830` twice.** The queued notice prints the first eight characters of the job UUID, and
  two jobs minted in the same millisecond share them - so two different songs look like they share a
  job. They do not: `01a12830-61dd-…` (Tera Suroor) and `01a12830-8944-…` (Ganesha). A longer slice,
  or the song's own id, would remove the ambiguity.
- **`pnpm worker:api` warns before it starts:** `Project directory 'apps/api' does not exist`,
  because the script passes `--project apps/api` and `--directory apps/api` together. The worker is
  unaffected - settings resolve from the module path, not the working directory, which is why every
  job ran and why `pipeline_version` was correct - so this is noise to tidy whenever someone is next
  in `package.json`.

## 4. The three recordings, measured

Read back from `analysis_results` for this run's three jobs; `Notes` is the `midi` artifact's own
`note_count`.

| Recording   | Source      | Duration | BPM    | Key              | Chords       | Chords JSON | MIDI  | Notes  | Job    |
| ----------- | ----------- | -------- | ------ | ---------------- | ------------ | ----------- | ----- | ------ | ------ |
| Jyoti       | 6,050,426 B | 246.8 s  | 89.1   | G major (0.731)  | 169 segments | 11,580 B    | 298 B | **35** | 16.3 s |
| Tera Suroor | 9,658,559 B | 344.9 s  | 117.45 | C# minor (0.824) | 170 segments | 12,030 B    | 269 B | **29** | 10.5 s |
| Ganesha     | 1,409,563 B | 62.2 s   | 107.67 | C# minor (0.264) | 40 segments  | 2,721 B     | 198 B | **19** | 2.4 s  |

Chord vocabulary as stored (`progression` in the artifact): Jyoti `C, D, G, Gm, Gmaj7, A#maj7`; Tera
Suroor `C#m7, C#maj7, C#sus2, G#maj7, Amaj7, C#`; Ganesha `C#, D#, F#m, B, Dm, F#`. Mean confidence
70% / 74% / 63%, coverage 92% / 88% / 79%, and `no_chord_ratio` 0.0 on all three - the detector
named a chord for the whole recording rather than falling back to "no chord".

**Tera Suroor is the number this release was about.** The audit that opened the chords work recorded
it as **0 notes and a 66-byte tempo map** - a download that opened to an empty score. The shipped fix
(`transition_min_prob=None`, commit `1e32e71`) gives **29 notes and 269 bytes** on the same 30 s
window, which is exactly what the spike predicted for that parameter
(`spike/basic-pitch-onnx/results.md`). Jyoti is **35** both before and after, also as predicted, and
Ganesha's 19 is a new measurement rather than a confirmation - the spike only ever ran the first two.

The caveat that travels with all three: this is still the **monophonic sketch of the first 30 s**
(`MYBAND_WORKER_MIDI_WINDOW_SECONDS`), not a transcription of the mix. Nothing here says the notes
are the _right_ notes.

## 5. MuseScore

All three downloaded files were opened with MuseScore Studio 4.7.5 and exported twice - to MusicXML
and to PDF - which is MuseScore's own importer parsing the bytes and rebuilding the score, not our
reader agreeing with itself.

| File              | Exported MusicXML | Exported PDF | MuseScore's notes | Tied continuations | Distinct onsets | Trailing note | Tempo marking |
| ----------------- | ----------------- | ------------ | ----------------- | ------------------ | --------------- | ------------- | ------------- |
| `jyoti.mid`       | 24,515 B          | 32,787 B     | 38                | 3                  | **35**          | 29.8 s        | 126           |
| `tera-suroor.mid` | 23,797 B          | 32,192 B     | 39                | 10                 | **29**          | 29.9 s        | 130           |
| `ganesha.mid`     | 25,035 B          | 31,518 B     | 24                | 5                  | **19**          | 25.8 s        | 108           |

Read as: **the scores are non-empty, the notes are visible, and the note counts are the ones the
pipeline reported.** Three details are worth being precise about rather than leaving as apparent
contradictions:

- **MuseScore counts more `<note>` elements than we do (38 / 39 / 24 against 35 / 29 / 19).** Every
  extra element is a **tie continuation**: a note held across a barline is one note in the MIDI and
  two elements in MusicXML. Subtract them and the counts are identical - 35, 29, 19 - which is also
  what `mido` reports for `note_on` messages in the files, and what `pretty_midi` reports. Nothing is
  doubled or invented.
- **MuseScore guesses the key signature, because the file has no key-signature event.** `mido` reads
  exactly three meta events in each file: `set_tempo`, a 4/4 `time_signature` that `pretty_midi`
  writes by default, and `track_name` = `melody`. MuseScore therefore infers a key from the notes;
  its `fifths` values (+3, +4, −2) do not match the analysed keys (G major, C# minor, C# minor), and
  this is not a disagreement about our analysis - the key we report comes from `analysis_results`,
  which the MIDI does not carry.
- **MuseScore writes its own tempo marking** (126 / 130 / 108) where the files declare 89.103 / 117.454
  / 107.666 BPM - verified from the raw `set_tempo` value (673378 µs per beat = 89.1 BPM for Jyoti).
  Ganesha's 108 is the declared tempo rounded; the other two are MuseScore's own convention and the
  cause is **not established** here. The note data is unaffected.

Artifacts from step 5 and 6: the downloads and the exports are in `%TEMP%\myband-beta\`, which is
ephemeral by design - the files are reproducible by uploading the three recordings again and pressing
the MIDI button (section 3), and the exports by running `MuseScore4.exe -o <out>.musicxml <in>.mid`.

## 6. Launch decision

**Yes - a closed beta of ten, once the four conditions below are met.** The reasoning, in one line
each:

- **B1 closed** - 248 passed, 0 skipped, 0 failed against a migrated database, and the database was
  left exactly as it was found.
- **B2 closed** - the whole path ran through the product's own screens, and the API answered nothing
  but 200 and 201.
- **B3, B4 and B5 closed earlier** and are unaffected by this run ([BETA_READY.md](BETA_READY.md)).
- **The one thing a test cannot close:** nothing here ran outside this machine. Production storage,
  production Supabase and RunPod are all unexercised (section 9).

The conditions: three are already somewhere in [RELEASE_READY.md](RELEASE_READY.md) - two on the cut
checklist and one as R2 in the register - and the second is what this run adds.

1. **The deployment reads `MYBAND_PIPELINE_VERSION=0.2.0`, for the API _and_ the worker, moved
   together** (B5). `apps/api/.env` is untracked and a stale value silently wins over the new
   default, so a deployment still pinned to `0.1.0` keeps stamping `0.1.0` on rows produced by the
   chords pipeline.
2. **Whatever box runs the suite sets `MYBAND_E2E=1` as well as `MYBAND_TEST_DATABASE_URL`**, or the
   report is "247 passed, 1 skipped" and looks green while one end-to-end case never ran (N1).
3. **A worker is alive and supervised.** R2 is the risk that most directly turns into "the app looks
   broken": with no worker running, nothing reaps a job whose worker died and the song says
   "Analysing" forever. The sweep at startup clears the backlog on the next worker start, so this is
   an alert, not a fix.
4. **Decide about Google sign-in before inviting anyone.** There is no `[auth.external.google]` block
   in `supabase/config.toml`, so on the local stack the login page's "Continue with Google" button
   has nothing behind it; only email and password were exercised. Either enable the provider on the
   deployed project (`apps/web/.env.example` lists the dashboard steps) or invite people who will use
   email.

Not a condition, a recommendation: **keep the previous web build, API image and worker revision
tagged for the whole beta.** The rollback in [RELEASE_READY.md](RELEASE_READY.md) (section 5) assumes
they exist.

## 7. Remaining risks

Inherited from the register, unchanged and not closed by this run: **R2** (a job is only reaped while
a worker process is alive), **R3** (nothing retries a failed job - a failed song is re-uploaded),
**R4**/**R5** (nothing in the bucket is ever deleted, uploads are unbounded, no quotas or billing),
**R10** (no restore rehearsed). Plus the deliberate gaps: no cancel path, no retry route, no song
sections, whole-object reads, one region.

New in this run, lettered `N` so nobody confuses them with the register's `R`:

- **N1 - "0 skipped" needs two environment variables, and one of them is opt-in.**
  `test_worker_e2e.py` skips itself unless `MYBAND_E2E=1`, and the command block in
  [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) sets only the database URL. A fresh box
  following that block gets one skip and a report that reads as green. Cheap fix: add the variable to
  the documented command, or drop the opt-in gate now that the case runs in seconds.
- **N2 - MuseScore shows a key and a tempo that are its own** (section 5). A beta user who opens the
  MIDI in MuseScore sees a guessed key signature and a different tempo marking from the ones on the
  song page, and may reasonably conclude one of them is wrong. The file carries no key signature
  because the pipeline does not write one; explaining that is cheaper than fixing it, but it should
  be written down somewhere a user will read.
- **N3 - the chord labels are unverified by ear.** The detector is confident (mean 70% / 74% / 63%,
  coverage 92% / 88% / 79%) and its vocabulary includes `C#sus2`, `A#maj7`, `Gmaj7`, `Edim/G` and
  `Dsus2`. Nothing in this run checked whether those are the chords a musician hears. That is the
  "5-8 labelled recordings and an ear on them" item the spike scoped at 2-3 days, and it is the most
  likely source of "this is wrong" from the cohort.
- **N4 - Ganesha is the weakest of the three, and it is the shape of the cohort's material.** A 62 s
  clip: key strength 0.264, chord mean confidence 63%, 40 segments. Short and sparse recordings are
  what the beta will mostly contain, so this is what to expect rather than an outlier to explain away.
- **N5 - one machine, one run each.** Windows 11, CPU only, the same box that produced every other
  measurement in these documents; timings vary 20-30% between runs.

## 8. Recommended first user cohort

What the product can honestly give someone today: a duration, a BPM, a key, a chord timeline with
confidence and two readings of it, a monophonic MIDI sketch of up to the first two minutes, and the
song's form written as labelled sections. What it cannot give them: a transcription of the mix, a
delete, a retry, or a quota. The first ten people should be chosen against that list rather than
against the ambition.

**Ten hand-picked people, in roughly this mix:**

1. **Five or six independent producers and songwriters you already know.** Reachable individually, so
   feedback arrives as "the third chord in the chorus is wrong" rather than "the chords are wrong" -
   and that difference is the difference between a fix and a mystery (N3).
2. **Two DAW users who use MIDI every day.** They will judge the sketch for what it is, and they are
   the people whose "this is useless because..." is worth more than a compliment. Set the expectation
   in the invite: the opening two minutes at most, one line, a starting point to drag in - not a
   transcription.
3. **One person who will try to break the upload rules.** A 250 MiB file, a `.flac`, a text file
   renamed `.mp3`, a file with no extension, a filename with an emoji in it. The rules are
   implemented (`file-rules.ts` client-side, `upload_rules.py` server-side) and this run only ever
   fed them three well-behaved MP3s.
4. **One person who will use a non-Latin title.** A Devanagari title has rendered correctly in the
   library before (`ज्ञानज्योतिः (Jyoti)`, from an earlier upload of the same recording), but nothing
   in _this_ run exercised it, and titles come straight off the filename.
5. **Nobody who depends on it.** No billing (R5), no retry (R3), nothing deleted (R4), one region,
   no restore rehearsed (R10).

**Who not to invite:** anyone uploading commercial masters they do not own - the bucket keeps
everything uploaded and nothing deletes it (R4/R5), so "we will remove it later" is not a promise
this release can make. Not a label, not a public sign-up link, not a mailing list.

**One operational note for the invite email:** whoever is in the cohort has to be told that a
recording can take a minute or two, because the pitch tracker costs about a second per second of
audio and the worker runs one job at a time. The three songs in this run took 16.3 s, 10.5 s and 2.4 s

- and a second worker is a separate process, not a setting.

**Corrected 2026-10-16, for the v0.4 release.** Two claims in this section were written for the
0.2.0/0.3.0 pipeline and were wrong by the time the release was cut: the MIDI cap is 120 s rather
than a fixed 30 s slice, and a song's form is one of the things a beta user does get. Section 8's
list above is corrected in place. Sections 1-7 and 9 are the measurements and the conditions of the
2026-10-10 run and are unchanged.

## 9. What this run does not settle

Said plainly, because the rest of the file is evidence and this is the edge of it:

- **Nothing ran in production.** Local Supabase on `127.0.0.1`, its S3 storage endpoint, no
  Cloudflare R2, no deployed API, no deployed web build, no RunPod. The R2 code path is the same
  client (`app/services/storage.py`) and this run proves the shapes, not the service.
- **Google sign-in was not exercised, and is not configured locally** (condition 4).
- **No human ear on the output.** MuseScore was driven through its CLI export - `-o file.musicxml`,
  `-o file.pdf`, exit code 0 - so the scores are parsed and rendered but no one looked at a window or
  listened. The PDFs in `%TEMP%\myband-beta\musescore\` are there for exactly that.
- **No second platform.** Windows 11 x86-64, CPU only, Python 3.12, one run each.
- **No failure path was induced** beyond what the suite covers: no corrupt upload, no worker killed
  mid-job, no storage outage, no unanalyzable audio through the browser.
- **Song sections** are still the next stage and still absent.

## 10. How this file is maintained

- **One sign-off per gate.** When B1 and B2 are re-measured for a later release, this file is
  replaced rather than appended to - the register accumulates, a sign-off does not.
- **Every claim carries its evidence**, and where a number is one run it says so. Where something was
  not established, it says that instead of being inferred.
- **The letters are stable.** `N1`-`N5` are named here so they can be cited from a commit, a ticket
  or a message; when one is fixed it gains a `_Closed_` line here, and if it graduates to a standing
  risk it gets an `R` id in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and keeps it.
- **It is read at the cut, at the deploy, and before the first invite goes out**, alongside
  [RELEASE_READY.md](RELEASE_READY.md) and the register - the three files answer three questions:
  what ships, whether it is fit to ship, and what we are knowingly shipping anyway.
