# v0.4 release sign-off

This is the last gate of the song-sections release: whether the tree can be tagged. It is written
after the release cleanup, which resolved exactly two items - **F1** (the pipeline version stamp) and
**F4** (the copy that still claimed a 30-second MIDI) - and changed no behaviour. Feature freeze was
held: no capability was added, no test was rewritten, and the four gates below were run on the
finished tree.

**Status: YES - v0.4 can be tagged and released. No blockers.** The evidence is the four gates in
section 4, the test run they rest on (282 passed / 1 skipped), and the two audits in sections 2
and 3. What is deliberately left is in section 5, marked POST-LAUNCH, and it is left because the
instruction was to classify rather than to fix it.

## 1. Scope of this pass

| Item | Resolution                                                                                                                                                                                                            | Files                                                                               |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| F1   | `MYBAND_PIPELINE_VERSION` moved `0.3.0` -> `0.4.0`, with the sections artifact recorded as the reason and the history comment extended, so a 0.4 row is distinguishable from a 0.3 one in `analysis_results.summary`. | `apps/api/app/core/config.py`, `apps/api/.env.example`, `PRODUCTION_READINESS.md`   |
| F4   | Every claim that the MIDI is "the first 30 seconds" corrected to the shipped cap: 120 s, clamped to the recording. Nothing else in the copy was touched.                                                              | `apps/web/features/marketing/copy.ts`, `docs/analysis-worker.md`, `BETA_SIGNOFF.md` |
| F2   | Classified POST-LAUNCH, not fixed: the sections-detection harness lives in `spike/`, which `.gitignore` line 44 keeps out of the repository, so a fresh clone cannot reproduce `MIDI_WINDOW_REPORT.md`'s measurement. | none, see section 5                                                                 |
| F3   | Classified POST-LAUNCH, not fixed: the funnel is uninstrumented - no analytics dependency and no `track(` call anywhere - so a beta would be run blind. Its fix is the first item of release 0.5.                     | none, see section 5                                                                 |

No product code changed. `apps/api/app/workers/*`, the routes, the schemas, the web app and the
tests are byte-identical to the tree the sections audit validated: this pass touched a settings
default, two comments, three prose claims and one gate line.

## 2. F1 - the pipeline version

The setting is the only thing that tells one stored result from another, and the register's own rule
is "bump it when the worker's output shape changes" ([PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)).
Sections changed that shape - a fourth artifact, and a `form` in `summary` - so the release that
ships them cannot stamp `0.3.0`.

| Where                              | Before                                | After                                                                                      |
| ---------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------ |
| `apps/api/app/core/config.py`      | `default="0.3.0"`                     | `default="0.4.0"`, plus a `0.3.0 -> 0.4.0` line in the history comment that names sections |
| `apps/api/.env.example`            | `MYBAND_PIPELINE_VERSION=0.3.0`       | `MYBAND_PIPELINE_VERSION=0.4.0`, plus the same one-line reason                             |
| `PRODUCTION_READINESS.md` line 44  | gate read `0.2.0`, two releases stale | gate reads `0.4.0`                                                                         |
| `apps/api/.env` (untracked, local) | `MYBAND_PIPELINE_VERSION=0.3.0`       | `MYBAND_PIPELINE_VERSION=0.4.0`                                                            |

**Why it is safe.** No test pins the literal. The suites that build rows declare their own
`PIPELINE_VERSION = "0.1.0"` (`test_queue.py`, `test_queue_batch.py`, `test_queue_sweep.py`,
`test_admin_metrics.py`, `test_midi_download.py`, `test_song_chords.py`, `test_song_sections.py`,
`worker_support.py`, `test_worker_heartbeat.py`), and the one test that cares about the stamping
contract compares against the setting rather than a constant - `test_upload_flow.py:144` asserts
`outcome.job.pipeline_version == get_settings().pipeline_version`. Section 4 is the proof of that:
282 passed, unchanged, with the new default in place.

**README.** There is no version literal there to update. `README.md` describes the pipeline and the
worker but never names a pipeline version, and searching every tracked `.md`, `.py`, `.ts` and
`.tsx` for `MYBAND_PIPELINE_VERSION` and for `0.3.0` finds no other reference to the setting.

**The one deliberate exception.** `apps/web/features/marketing/demo-analysis.ts` still exports
`PIPELINE_VERSION = "0.2.0"`, and its comment now says why: the panel's figures are one real 0.2.0
row, so a badge that tracked the setting would credit a 0.4.0 run for numbers it did not produce.
The badge stays pinned to the data until the demo is re-run against a current job. Historical
documents - `MIDI_WINDOW_REPORT.md`, `RELEASE_READY.md`, `BETA_READY.md`, `docs/WIREFRAMES.md` -
keep their `0.2.0` and `0.3.0` mentions for the same reason: they are the record of what those
releases shipped.

## 3. F4 - the "first 30 seconds" copy

The cap has been 120 s, clamped to the recording, since `v0.3-midi-window`. The audit found one
user-facing sentence that still said 30 seconds and two documents that stated it as current fact.
All three are corrected:

| Surface                     | Before                                                                                  | After                                                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Landing page FAQ            | "a monophonic sketch of the melody from the first 30 seconds"                           | "covers up to the first 120 seconds, clamped to the recording - a song shorter than two minutes is transcribed whole" |
| `docs/analysis-worker.md`   | "a monophonic 30-second sketch", stated in the present tense                            | "a monophonic sketch of a bounded window (up to two minutes)"                                                         |
| `BETA_SIGNOFF.md` section 8 | "a **30-second monophonic MIDI sketch**", and "first 30 seconds" in the invite guidance | "up to the first two minutes", and "the opening two minutes at most"                                                  |

`BETA_SIGNOFF.md` also carried "song sections" in the list of what the product cannot give a beta
user, which this release makes false, so that list is corrected in the same sentence. The file's
dated sections - what was run, what was measured, what the run did not settle - are untouched, and a
note dated **2026-10-16** records the correction and says which sections it covers.

**Audited and left alone, on purpose.** `MIDI_WINDOW_REPORT.md` compares 0.2.0 against 0.3.0 by
design and its 30-second column is a measurement, not a claim. `RELEASE_READY.md` and `BETA_READY.md`
are dated release records. `docs/midi-transcription-options.md` already describes the cap through
`MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS`. `apps/api/tests/test_config.py`'s 30-second comment explains
what the legacy variable name still does, which is accurate. The `30 seconds` hits in
`supabase/seed.sql` are seed timestamps. The demo panel's `windowSeconds: 30` is the measured window
of the demo run rather than a statement about the product, nothing renders it, and the note count
beside it is honest for that run.

## 4. The gates

All four were run on the finished tree, from the repository root, with the local Supabase
(`127.0.0.1:54322`) migrated - the database-backed cases need it, or they skip themselves.

| Command          | Result                                                                                          | Exit |
| ---------------- | ----------------------------------------------------------------------------------------------- | ---- |
| `pnpm test:api`  | **282 passed, 1 skipped, 9 warnings in 29.16 s** - the skip is the `MYBAND_E2E` end-to-end gate | 0    |
| `pnpm lint`      | clean - `eslint .` in each package, no findings                                                 | 0    |
| `pnpm typecheck` | clean - `tsc --noEmit` in each package                                                          | 0    |
| `pnpm build`     | clean - 5 app routes plus middleware compiled; `/` 54.1 kB, 286 kB First Load, shared JS 103 kB | 0    |

Two extra checks, because this pass edited Python and all three document types: `pnpm lint:api` (ruff)
answers **All checks passed**, and every line this pass changed is prettier-clean. Both formatters do
still have pre-existing complaints, listed in section 5 as POST-LAUNCH rather than blockers:
`ruff format --check` wants one committed test file reformatted, and `prettier --check` wants two
tables re-padded, one of which sits in a file this pass edited. Neither touches a changed line,
neither formatter is part of the four gates, and re-padding tables was not this pass's scope.

## 5. Answer

### Can v0.4 be tagged and released?

**YES.**

### Blockers

None.

The release does carry one deploy-time condition, which is an action rather than a defect in the
tree: `MYBAND_PIPELINE_VERSION=0.4.0` has to be set wherever the API **and** the worker run. The
default in `config.py` now reads `0.4.0`, but an environment that still pins `0.3.0` wins over that
default silently, which is how the previous release came to record a stale stamp. The local `.env`
is updated and is git-ignored; deployed environments are not reached by this commit. Step 0 of
section 6 covers it.

### POST-LAUNCH

| Item                                                                                                                                                                       | Classified as |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| **F2** - the harness behind the MIDI window decision is not in the repository: `spike/` is git-ignored (line 44), so a fresh clone cannot reproduce that measurement.      | POST-LAUNCH   |
| **F3** - the funnel is uninstrumented: no analytics dependency, no `track(` call, so beta behaviour cannot be read. Item 4 of release 0.5.                                 | POST-LAUNCH   |
| The landing demo is a 0.2.0 run (`PIPELINE_VERSION`, a 30 s note count). Honest, and a release behind. Item 8 of release 0.5.                                              | POST-LAUNCH   |
| `ruff format --check` would reformat one committed file: `apps/api/tests/test_config.py`, the parametrised signature at line 132. Pre-existing and outside the four gates. | POST-LAUNCH   |
| `prettier --check` would reformat two pre-existing tables: the `R1` row in `PRODUCTION_READINESS.md`, and the stage table in `docs/analysis-worker.md`. Whitespace only.   | POST-LAUNCH   |
| Section naming (verse / chorus) stays letters until there is funnel data to justify lyrics work - releases 0.6 and 0.7 in [NEXT_3_RELEASES.md](NEXT_3_RELEASES.md).        | POST-LAUNCH   |
| No retry route, nothing deleted, no billing, no restore rehearsed (`R3`-`R5`, `R10`). Known, decided, and unchanged by this release.                                       | POST-LAUNCH   |

## 6. The release commands

Run from the repository root, in PowerShell, on a tree that is still at `440cc98` on `main` with the
release diff unstaged. Nothing below has been run yet. Step 0 changes directory and changes back;
every other step assumes the repository root.

**Step 0 - the deploy-time condition.** Not a repository change; do it before the deploy, not before
the tag:

```powershell
# Wherever the API and the worker run, both environments:
#   MYBAND_PIPELINE_VERSION=0.4.0
# Locally, apps/api/.env already reads 0.4.0. Confirm what the process actually loads -
# from apps/api, because the import is `app.core.config` and the .env sits beside it:
cd apps/api
uv run python -c "from app.core.config import get_settings; print(get_settings().pipeline_version)"
cd ..
# expect: 0.4.0
```

**Step 1 - pre-flight.** The tree must be the audited one, and the remote must not have moved:

```powershell
git status --short          # 27 modified, 9 untracked (this file is one of them); nothing staged
git rev-parse --abbrev-ref HEAD   # main
git --no-pager log --oneline -1   # 440cc98 (HEAD -> main, tag: v0.3-midi-window, origin/main)
git fetch origin
git rev-list --count origin/main..main   # 0 - nothing unpushed, so the merge can fast-forward
```

**Step 2 - the release branch, then commit.** Branch first so the merge is a recorded fast-forward
rather than a commit made on `main`:

```powershell
git switch -c feat/song-sections
git add -A
git status --short          # every path staged, nothing left in the second column
git commit -m "feat: song sections, and the v0.4 release prep" -m "Sections are detected, stored as a sections artifact, read back through GET /songs/{id}/sections and drawn as a form strip on the song page. MYBAND_PIPELINE_VERSION moves to 0.4.0 so a 0.4 row is distinguishable from a 0.3 one, and the MIDI copy that still said 30 seconds now states the shipped 120 second cap." -m "Gates on this tree: pnpm test:api 282 passed / 1 skipped, pnpm lint, pnpm typecheck, pnpm build - all exit 0. See V0_4_RELEASE_SIGNOFF.md."
```

**Step 3 - merge into `main`.** `--ff-only` on purpose: if it refuses, the branch has diverged and
the release is not the thing that was audited:

```powershell
git switch main
git merge --ff-only feat/song-sections
git --no-pager log --oneline -2
git rev-list --count feat/song-sections..main   # 0
```

**Step 4 - tag.** Annotated, matching `v0.3-midi-window`:

```powershell
git tag -a v0.4-sections -m "v0.4 song sections: sections artifact, route and song-page form strip; pipeline version 0.4.0; MIDI copy corrected to the shipped 120 s cap"
git show --stat --oneline v0.4-sections
```

**Step 5 - push.** `main` has **no upstream configured** (`git rev-parse @{u}` answers "no upstream
configured for branch 'main'"), so the first push needs `-u`. Commit first, then the tag:

```powershell
git push origin main --dry-run     # expect: a fast-forward from 440cc98
git push -u origin main
git push origin v0.4-sections
git --no-pager log --oneline -1 origin/main
git ls-remote --tags origin v0.4-sections
```

**Step 6 - verify the release.** The tree should come back clean: every path in step 2 is committed,
and `apps/api/.env` never appears in `git status` at all because it is ignored.

```powershell
git status --short        # expect: no output
git log --oneline -1      # the release commit, on main, tagged v0.4-sections
```
