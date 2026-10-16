# Production readiness

What has to be true before MyBand.video is opened to the public, and what is knowingly still
missing. It is a register rather than a promise: every risk below is one we have looked at and
made a decision about, and the decision is written next to it.

**Status: pre-beta.** The pipeline produces duration, BPM, key, a chord timeline, a section list
and a MIDI sketch; the public beta is the next milestone. The mechanics the product rests on - the
upload lifecycle, the queue state machine, the analysis worker, the storage seam - are implemented
and covered by `pnpm test:api`;
[upload-flow.md](docs/upload-flow.md), [queue-state-machine.md](docs/queue-state-machine.md),
[analysis-worker.md](docs/analysis-worker.md) and [schema.md](docs/schema.md) are the
contracts they keep.

## Risk register

Ordered by what would hurt most if it landed, not by likelihood. Ids are stable: code and docs
cite them, so a retired risk keeps its number and gains a _Closed_ line rather than being
deleted.

| Id  | Risk                                                                 | Why it bites                                                                                                                                                                                                                                                                                                     | What stands in for a fix today                                                                                                                                                                                                                           |
| --- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | The API's own scoping is the only thing between two accounts         | `apps/api` connects as the `postgres` role, which bypasses RLS (`app/core/config.py`), so the RLS matrix protects the Data API path and not this service. One forgotten `where user_id = %s` leaks a row, and no policy catches it.                                                                              | One ownership check per route, where unknown, another account's and soft-deleted ids all answer `404`; `tests/test_api_routes.py`, `tests/test_rls.py` and `tests/test_midi_download.py` and `tests/test_song_chords.py` assert it.                                                      |
| R2  | A job is only reaped while a worker process is alive                 | The orphan sweep runs inside the worker loop (`app/workers/runner.py`, `MYBAND_WORKER_REAP_SECONDS`), so with no worker running nothing fails a job whose worker died: the song keeps saying "Analysing" and nothing counts it.                                                                                  | The sweep runs once at startup, so the next worker that starts clears the backlog; `/admin/metrics` reports `oldest_in_flight_seconds` and `reaped_recently`. Keep a worker alive, and alert on the age.                                                 |
| R3  | Nothing retries a failed job automatically                           | `reap_stale` fails rather than requeues and no route re-enqueues, so a transient failure - a worker out of memory, a bucket `503` - reaches the user as a song that stays failed until they retry.                                                                                                               | Deliberate: a retry is a new row and the queue does not start work behind a user's back (`docs/queue-state-machine.md`). The job keeps `error_code` and `attempts`, so the support script can say what happened.                                         |
| R4  | Nothing in R2 is ever deleted                                        | No producer or drainer for `storage_gc_queue`, no sweeper for abandoned `pending` uploads, and no route that deletes a song - so a hard-deleted song's audio stays in the bucket forever, silently. A cost and retention item rather than a correctness one: once the row is gone nothing references the object. | An R2 lifecycle rule as the backstop. `app/models/storage_gc.py` (enqueue, list_due, complete, retry) and `uploads.list_pending_expired` exist for the missing workers; nothing calls them yet. See [upload-flow.md](docs/upload-flow.md).               |
| R5  | Upload cost is unbounded                                             | No quota and no rate limit anywhere in the API. The 200 MiB cap is per file, R2 has no bucket-side size limit to fall back on, and `checksum_expected` is recorded but never verified - so one account can fill the bucket.                                                                                      | The API's own rules (`check_object`, `resolve_content_type`) and the presigned URL's scope, which is the only gate R2 has, plus an R2 lifecycle rule for strays. A per-account quota is the first thing to add when billing arrives.                     |
| R6  | The client contract is hand-mirrored                                 | `packages/shared` mirrors the Pydantic models field for field. A field added on one side and not the other is caught by a test or by a screen breaking, not by a compiler.                                                                                                                                       | Codegen from the OpenAPI schema is deliberately deferred (README, "Conventions"), and every shared schema _parses_ the API's answer instead of casting it, so drift fails loudly at the boundary.                                                        |
| R7  | The web app has no test runner                                       | Auth, upload and download behaviour on the web side is not covered by tests. Adding Vitest and React Testing Library was decided against for this sprint: it is a toolchain to own, and the API's suites already pin the contracts the UI parses.                                                                | `pnpm lint`, `pnpm typecheck` and `pnpm build` must pass, plus the manual checklist below on every change to a screen.                                                                                                                                   |
| R8  | A deployment with no metrics token publishes no queue visibility     | The endpoint fails closed - `404` with no token outside a local development run, `401` when a token is configured and not presented - which is the right default, but an operator then has nothing to look at.                                                                                                   | Set `MYBAND_METRICS_TOKEN` in every non-local environment and open `/admin/metrics` after each deploy (gate below). Interactive docs are off in production, because `/openapi.json` publishes every route including this one.                            |
| R9  | Email sign-in depends on the project's SMTP                          | Locally, sign-up mail lands in Inbucket. A production project left on the default sender is rate-limited and will drop confirmation emails, so sign-up appears to do nothing.                                                                                                                                    | Configure a real SMTP provider in the Supabase project before opening sign-ups, and decide whether "Confirm email" is on - the web app handles both (`features/auth/actions.ts`).                                                                        |
| R10 | A lost database is a lost library, and no restore has been rehearsed | Supabase takes backups; nothing in this repository proves they restore, and the objects those rows point at live in R2, which no database snapshot covers.                                                                                                                                                       | `supabase/migrations` is the schema's source of truth and `db reset` replays it, so an empty database can be rebuilt in minutes - with no audio, which is what R4 means for the library rather than for a single song. Rehearse one restore before beta. |

## Before public beta

Each line is a thing to do and see, not a thing to believe. They are the gates the register
above leaves open.

**Configuration**

- [ ] `MYBAND_ENV=production` (this is what switches the interactive docs off), `MYBAND_LOG_LEVEL=info`
- [ ] `MYBAND_CORS_ORIGINS` names the deployed web origin and nothing else - not a wildcard
- [ ] `MYBAND_METRICS_TOKEN` is set, and `/admin/metrics` answers counts with it and `401` without
- [ ] `MYBAND_PIPELINE_VERSION` matches what the deployed worker writes - `0.4.0` since song sections (bump it when the worker's output shape changes)
- [ ] `apps/web`: `NEXT_PUBLIC_API_BASE_URL` and `API_BASE_URL` both point at the API; the Supabase URL and publishable key are the project's

**Storage**

- [ ] The bucket exists with the CORS and content-type settings in [upload-flow.md](docs/upload-flow.md), `audio/midi` and `application/json` included
- [ ] An R2 lifecycle rule covers stray objects (R4, R5)
- [ ] R2 credentials are scoped to this bucket, and rotating them is a documented step

**Queue and workers**

- [ ] At least one worker is running (`pnpm worker:api`, audio dependency group installed) and it is restarted if it dies
- [ ] `oldest_queued_seconds` falls on `/admin/metrics` after an upload, and reaches `Analysing` on the dashboard
- [ ] A killed worker's job is reaped: `reaped_recently` moves, and the row shows `failed` with `error_code = 'stale'`
- [ ] An alert exists on `oldest_in_flight_seconds` and on `failed_recently` (R2)

**Database**

- [ ] Migrations are applied with the CLI (`supabase db push`), never through the dashboard SQL editor
- [ ] `auto_expose_new_tables = false` on the cloud project, as it is locally
- [ ] One restore rehearsed, and the person who would do it at 2am knows where this file is (R10)

**Auth**

- [ ] Google provider configured, with `https://<project-ref>.supabase.co/auth/v1/callback` registered in Google
- [ ] Site URL and redirect URLs list the production origin (and preview deployments, if they are used)
- [ ] SMTP configured, "Confirm email" decided, and one sign-up read end to end in the production inbox (R9)

**Support**

- [ ] A user can reach a human from the product or from the confirmation email
- [ ] Whoever answers has `/admin/metrics`, the queries in [queue-state-machine.md](docs/queue-state-machine.md), and the failure codes in [analysis-worker.md](docs/analysis-worker.md)

## Manual web validation checklist

R7's stand-in. The web app has no test runner, so these are the checks a change to a screen
has to survive, alongside `pnpm lint`, `pnpm typecheck` and `pnpm build`. They are written as
things to see, because each one is a promise the API makes that the page has to keep.

**Auth**

- [ ] Sign in with email and with Google; both land on the dashboard
- [ ] `/dashboard` while signed out redirects to `/login`; sign out returns to the landing page

**Upload**

- [ ] An MP3 and a WAV both upload: the bar reaches 100%, then "Confirming the file and queueing the analysis..."
- [ ] The row appears with its title, size and content type, and the badge moves Queued → Starting → Analysing → Analysed
- [ ] A `.flac`, and a file over 200 MiB, are refused in the browser with a message and no request
- [ ] Choosing the same file twice in a row works (the input is cleared after each choice)

**While a job is in flight**

- [ ] "Analysing - this list updates itself." appears under Library, and the badge changes without a refresh
- [ ] Switching tabs for a minute and returning shows a current list, not a stale one
- [ ] The line disappears once nothing is in flight, and the polling stops with it

**Download**

- [ ] MIDI on an analysed row downloads a file named after the song, with a `.mid` extension
- [ ] A row whose job has not succeeded shows no MIDI button at all

**Failure paths**

- [ ] Stop the API and reload `/dashboard`: the page still renders the uploader and says "The library could not be loaded.", rather than an error screen
- [ ] A failing MIDI request shows its message in the row and leaves the button usable again

**Build**

- [ ] `pnpm lint`, `pnpm typecheck` and `pnpm build` are clean
- [ ] The dashboard route's First Load JS has not jumped by tens of kB (it is ~74 kB / ~302 kB with the current screens)

## Deliberate gaps, accepted for beta

Known, decided, and not being fixed in this sprint:

- **No cancel path.** `canceled` is a status the schema accepts and nothing produces
  ([queue-state-machine.md](docs/queue-state-machine.md), "Deliberately absent").
- **No retry route.** A song that failed can only be re-uploaded, which creates a new song;
  nothing re-enqueues an existing one (R3).
- **Sections are labelled, not named.** The stage ships - the `sections` artifact, its route and
  the song page's form strip - but a section is a letter (`A B A B C`), not a verse or a chorus,
  because naming one takes the lyrics. Chords left this list with the chords release: the stage,
  the `chords` artifact and the song page's timeline.
- **No GPU dispatcher.** A worker is a process someone runs; the RunPod path is not wired into
  the queue ([upload-flow.md](docs/upload-flow.md), "Deliberately not here yet"), and production
  therefore requires no RunPod credentials: `Settings._require_production_secrets` demands only
  what running code reads. The commit that lands the dispatcher puts them back in that map, and
  `apps/api/tests/test_config.py` pins both halves of the decision.
- **No quotas, plans or billing** (R5).
- **No frontend test framework** (R7), and **no OpenAPI codegen** (R6).
- **Whole-object reads.** A download link fetches the entire artifact; there is no ranged read
  for a player ([upload-flow.md](docs/upload-flow.md)).
- **One region.** Postgres and the bucket each live in one place, and there is no failover story.

## Commands this rests on

```powershell
pnpm test:api        # API, worker and database suites; the database cases skip themselves
                     # unless MYBAND_TEST_DATABASE_URL points at a migrated database
pnpm lint            # ESLint across the JS packages
pnpm typecheck       # tsc --noEmit, strict
pnpm build           # the production build, which is what catches a bad Server Component

$env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
```

## How this file is maintained

- **A risk gets an id when it is accepted, and keeps it.** Closed risks gain a `_Closed_` line
  saying what closed them; the number is never reused, so a citation in code or in a doc stays
  meaningful.
- **No risk without a decision.** "We will fix it later" is a decision only when it says what
  stands in for the fix in the meantime, and where.
- **Point at code, not at intent.** Every mitigation above names a module, a route, a test or a
  setting that exists today.
- **Re-read it at each milestone** - before song sections, before the beta - and
  at each deploy that changes one of the gates.
