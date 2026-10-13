# Beta readiness: blockers B3, B4 and B5 closed

This is the certificate for three of the five launch blockers in [RELEASE_READY.md](RELEASE_READY.md).
That file describes one release and keeps the blockers; this one closes three of them and restates
nothing it already says. The standing platform risks stay in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) - this file does not touch the register.

**Status: B3, B4 and B5 closed on 2026-10-11, on top of `8bf2d88`, as an uncommitted release-prep
change. B1 and B2 remain open, so the release is not beta-ready.**

Every number below was produced by the command beside it, in one sitting, on the Windows
development box. Nothing here is estimated.

## 1. Where the three stand

| Blocker | What closed it                                                                                      | The measurement                                                                                      |
| ------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| B3      | `spike/` added to `.gitignore` and `.prettierignore`                                                | `git add -A --dry-run` stages 12 paths and none under `spike/`; `format:check` fell from 41 to 7     |
| B4      | `_require_production_secrets` no longer demands RunPod credentials; two tests pin both halves       | a production boot with the RunPod credentials empty succeeds, and a missing R2 secret is still fatal |
| B5      | the default, `.env.example` and this machine's `.env` all read `0.2.0`; stale chord prose corrected | `get_settings().pipeline_version` reports `0.2.0`, measured after the `.env` fix                     |

## 2. B3 - the cut can no longer swallow `spike/`

**The change** for this blocker is two lines of configuration, one in each ignore file:

```diff
diff --git a/.gitignore b/.gitignore
@@ -38,3 +38,7 @@ Thumbs.db
 pnpm-debug.log*
+
+# Local spike scratch (spike/) - hundreds of MB of experiments that are not part of
+# the product. Never staged: a release commit must not be able to swallow it.
+spike/
```

`.prettierignore` gained the same entry with its own comment, so the scratch is neither committed
nor formatted.

**The measurement.** Both the directory and everything inside it are ignored, and the rule that
matches is the new one:

```console
$ git check-ignore -v spike
.gitignore:44:spike/    spike
$ git check-ignore -v spike/basic-pitch-onnx
.gitignore:44:spike/    spike/basic-pitch-onnx
```

The scan that matters is what a commit would actually take, not what the ignore file says:

```console
$ git add -A --dry-run
add '.gitignore'
add '.prettierignore'
add 'PRODUCTION_READINESS.md'
add 'README.md'
add 'apps/api/.env.example'
add 'apps/api/README.md'
add 'apps/api/app/core/config.py'
add 'apps/api/tests/test_config.py'
add 'docs/upload-flow.md'
add 'BETA_READY.md'
add 'RELEASE_READY.md'
add 'docs/midi-transcription-options.md'
```

Twelve paths: the nine tracked files this work changed, the two docs it wrote (this one and
[RELEASE_READY.md](RELEASE_READY.md)), and `docs/midi-transcription-options.md`, which it did not
touch and does not vouch for - see section 6. **No path under `spike/`.** The other heavy directories
were already covered and still are - `node_modules/` (`.gitignore:2`), `.next/` (`.gitignore:6`),
`.venv/` (`.gitignore:26`, which is what matches `apps/api/.venv`) and `.env` (`.gitignore:19`).

**The same scan found a second thing: two test files report as modified when they are not.**
`apps/api/tests/worker_support.py` and `apps/api/tests/test_worker_heartbeat.py` appear as ` M` in
`git status`, but both are absent from the list above and

```console
$ git diff --quiet -- apps/api/tests/worker_support.py apps/api/tests/test_worker_heartbeat.py
$ echo $?
0
```

exits 0 - byte-identical to `HEAD`, and nothing for `git add` to stage. It is a stale stat cache
reporting a timestamp rather than a content difference. Treat a bare ` M` on a file that is absent
from `--dry-run` as this, and do not "fix" it by staging it.

**What this does not do.** It does not delete `spike/`: it is still on disk at the size
[RELEASE_READY.md](RELEASE_READY.md) records, because the change adds two lines and removes none. It
also does not help a checkout that predates the prep commit - the entries have to be committed
_before_ the release commit, which is why they are part of this change rather than a follow-up.

## 3. B4 - a production boot no longer asks for secrets nothing reads

**The change.** `Settings._require_production_secrets` (`apps/api/app/core/config.py:178`) now
requires exactly the five settings the running code reads - `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` - and says
in its own docstring why RunPod's two are not among them: nothing calls RunPod yet, and demanding
them means either a placeholder secret or a deploy blocked for no functional gain. The dispatcher
commit puts them back and flips the test that pins their absence.

**The measurement, three ways.**

A production boot with the two RunPod credentials empty succeeds:

```console
$ MYBAND_ENV=production, RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID empty, the five real ones supplied
booted, env = production | runpod key set = False | runpod endpoint set = False
exit 0
```

That boot is precisely what the old rule refused, and the diff is the reason rather than a
remembered one - the two empty values are the two names the old `required` dict would have listed:

```console
empty runpod values the old validator would have listed: ['RUNPOD_API_KEY', 'RUNPOD_ENDPOINT_ID']
```

And it still fails closed where it should. With `R2_SECRET_ACCESS_KEY` genuinely missing, the boot
is refused, the message names that setting, and it does not name RunPod:

```console
validator line: ["Value error, missing settings required in production: R2_SECRET_ACCESS_KEY ..."]
names R2_SECRET_ACCESS_KEY: True | names RUNPOD_API_KEY: False
```

Both halves are pinned by tests, so this cannot drift silently:
`tests/test_config.py:31` requires a production boot to name the missing R2 key _and_ asserts
`"RUNPOD_API_KEY" not in message`, and `tests/test_config.py:49` asserts a production boot succeeds
with both RunPod fields empty. `pnpm test:api` reports **134 passed**, one more than the 133 in
[RELEASE_READY.md](RELEASE_READY.md) because the second of those tests is new.

## 4. B5 - the pipeline version, and the prose that described the pre-chords world

**The tracked change.** The default in `apps/api/app/core/config.py` is `0.2.0` and
`apps/api/.env.example` ships `MYBAND_PIPELINE_VERSION=0.2.0`, so a fresh deployment and a fresh
clone both start on the new value. The prose is corrected where it had gone stale, and no longer
claims chords have no stage and no screen:

| File                          | What it says now                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------- |
| `README.md:312`               | "Not implemented yet" is song sections alone; the worker reads chords and writes MIDI |
| `PRODUCTION_READINESS.md:7`   | the pipeline produces a chord timeline and a MIDI sketch                              |
| `PRODUCTION_READINESS.md:124` | sections are the next stage; chords left the list with the chords release             |
| `docs/upload-flow.md`         | `GET /songs/{id}/chords`, the artifact it reads and the download's `audio/midi`       |
| `apps/api/README.md`          | the chords route and the `chords` artifact as shipped                                 |

**The catch, which is why this section is not one line.** The default is only a default. An explicit
value beats it, and `apps/api/.env` is untracked (`apps/api/.env` is ignored by `.gitignore:19`), so
while it still pinned the old version the tracked files all said `0.2.0` and the running application
said `0.1.0` - measured, before the edit:

```console
pipeline_version = 0.1.0
```

and after it:

```console
$ uv run --project apps/api --directory apps/api python -c "from app.core.config import get_settings; print(get_settings().pipeline_version)"
pipeline_version = 0.2.0
```

This is why B5's checklist line in [RELEASE_READY.md](RELEASE_READY.md) is about the deployed worker
and API agreeing, not about the repository: **a deployment whose `.env` or platform environment
still says `0.1.0` keeps stamping `0.1.0` no matter what this branch contains**, and the API and the
worker must be moved together or stored results become uninterpretable in exactly the way the
version stamp exists to prevent. Already-stamped rows are not rewritten; they keep the version that
produced them.

**What pins it.** The contract test `apps/api/tests/test_upload_flow.py:144` asserts the job row's
`pipeline_version` equals `get_settings().pipeline_version` - the stamping contract, not the literal
`0.2.0`, so it cannot fail if the default drifts. The literal lives in the config default, in
`.env.example`, and in the checklist line at `PRODUCTION_READINESS.md:44`, and those three are what
have to be updated when the stage list changes.

## 5. The runs this rests on

All of these were run on 2026-10-11, on the working tree that `git add -A --dry-run` lists in section 2. Nothing was measured on a different revision.

| Command                                              | Result                                          |
| ---------------------------------------------------- | ----------------------------------------------- |
| `pnpm test:api`                                      | **134 passed, 114 skipped, 0 failed** in 8.65 s |
| `pnpm lint`                                          | exit 0                                          |
| `pnpm typecheck`                                     | exit 0                                          |
| `pnpm build`                                         | exit 0, 7/7 static pages generated              |
| `pnpm lint:api` (ruff check)                         | `All checks passed!`, exit 0                    |
| `ruff format --check --config apps/api/... apps/api` | `78 files already formatted`, exit 0            |
| `pnpm format:check`                                  | 7 files - all pre-existing, see section 6       |
| `git add -A --dry-run`                               | 12 paths, none under `spike/`                   |
| `git check-ignore -v spike`                          | `.gitignore:44:spike/`                          |

**Run the API suite from a shell with none of these exported.** Fourteen of its tests assert the
behaviour of settings that are _absent_, so `MYBAND_ENV`, `DATABASE_URL`, the `R2_*` names,
`SUPABASE_*` and `RUNPOD_*` left in the environment make them fail for a reason that has nothing to
do with the code: with `MYBAND_ENV=production` and sentinel `R2_*` values exported, the same tree
reported 14 failed / 120 passed / 114 skipped (`test_auth.py`, `test_storage.py`), and on a clean
shell it reports 134 / 114 / 0. Check the environment before believing a red run - and clear the
variables you exported for one experiment before running another.

## 6. What this file does not certify

- **B1 and B2 are open and untouched.** The 114 skips are still 114 skips: no database was pointed
  at these tests, and the HTTP path was still not exercised. Sections 2-4 say nothing about either.
- **`docs/midi-transcription-options.md` is not vouched for.** It is untracked, its explanation of
  empty MIDI files is still the stale one, and it is _not_ ignored - `git add -A` would take it into
  the prep commit, which is the one path in section 2's list that this work did not touch. It is
  still the open decision in [RELEASE_READY.md](RELEASE_READY.md)'s cut checklist: correct it and
  commit it, or delete it, but decide before the prep commit rather than during the cut.
- **The 7 prettier offenders are not new to this prep change, and are not fixed here.** Every one of
  them already failed at the branch head `8bf2d88`, which is the question that matters for this
  change, and the one file it edited that is not an offender - `apps/api/README.md` - was clean then
  and is still clean. [RELEASE_READY.md](RELEASE_READY.md) asked whether the markdown offenders
  failed _before_ the branch touched them; measured on 2026-10-11 by formatting each `main`
  (`4428e2d`) blob with prettier and comparing the bytes, the answer is not one answer:

  | Offender                                                                  | On `main` | Reading                                                            |
  | ------------------------------------------------------------------------- | --------- | ------------------------------------------------------------------ |
  | `docs/upload-flow.md`, `docs/queue-state-machine.md`                      | fails     | pre-existing - the branch did not start them                       |
  | `README.md`, `PRODUCTION_READINESS.md`, `docs/analysis-worker.md`         | clean     | the release's own doc edits introduced them                        |
  | `apps/web/features/uploads/jobs.ts`, `.../components/library-refresh.tsx` | clean     | clean as stored; only this worktree's CRLF makes prettier disagree |

  Seven files, three causes, and only the middle row is prettier debt this release created. All three
  are the chords work's own prose, so the fix belongs in the chore commit
  [RELEASE_READY.md](RELEASE_READY.md) already asks for, not inside a blocker's change - the number
  that moved here is 41 files to 7, and the 34 that went are exactly the `spike/` tree.

- **No RunPod or GPU path was created.** B4 removes a demand for credentials nothing reads; it does
  not add a dispatcher, and the client in [RELEASE_READY.md](RELEASE_READY.md)'s warning about
  `internal_error` rates is still a process someone runs by hand.
- **The `.env` fix cannot travel.** `apps/api/.env` is ignored by git, so it is absent from
  section 2's list and no commit carries it anywhere. Every other machine and the deployment have
  their own, and section 4 is what has to be done to them.
- **B5's deployment half is a deploy-time step.** That the deployed worker and API agree on `0.2.0`
  is not something the repository can assert, which is why it stays a tick-box in the launch
  checklist rather than a claim here.

## How this file is maintained

- It certifies **three blockers**, not a release and not the platform. When B1 and B2 close they get
  their _Closed_ lines in [RELEASE_READY.md](RELEASE_READY.md) and the status line at the top of this
  file changes; this file does not accumulate release history, and the register keeps the standing
  risks.
- The letters belong to [RELEASE_READY.md](RELEASE_READY.md) and are only referenced here. That
  file's B3, B4 and B5 entries gained the _Closed_ lines this file backs up.
- Every claim above is a command with its output. Re-run them before the cut rather than trusting
  the text; if one no longer reproduces, the blocker it closed is open again until it does.
