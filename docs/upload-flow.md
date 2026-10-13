# Upload to analysis job

The objective in one sentence: a signed-in user drags an MP3 or WAV onto the
dashboard and ends up with a `songs` row, an `analysis_jobs` row in `queued`, and
a job id they can poll - while **no audio byte ever passes through FastAPI**.

The schema these rows are written into is frozen (`docs/schema.md`); everything
below is the API on top of it.

## End to end

```text
Browser                FastAPI                   Postgres          Cloudflare R2      Dispatcher
(dashboard)            (apps/api)                (Supabase)        (bucket)           (next phase)
   |                       |                         |                  |                |
   | 1  POST /uploads/presign                        |                  |                |
   |    Authorization: Bearer <access token>         |                  |                |
   |---------------------->|                         |                  |                |
   |                       | verify JWT (JWKS / secret)                 |                |
   |                       | validate ext+MIME, declared bytes <= 200MB |                |
   |                       | insert uploads (pending, expires_at)       |                |
   |                       |------------------------>|                  |                |
   |                       | sign PUT URL (SigV4, TTL == expires_at)    |                |
   | 2  201 {upload_id, object_key, upload_url, method, headers, expires_at}            |
   |<----------------------|                         |                  |                |
   | 3  PUT <upload_url>   (XHR, upload.onprogress -> progress bar)     |                |
   |------------------------------------------------------------------->|                |
   |<-------------------------------------------- 200 + ETag -----------|                |
   | 4  POST /uploads/complete {upload_id, title?, artist?, project_id?}|                |
   |---------------------->|                         |                  |                |
   |                       | HEAD object             |                  |                |
   |                       |------------------------------------------->|                |
   |                       |<-- ContentLength, ContentType, ETag -------|                |
   |                       | check: >0, <=200MB, MIME allowed for ext   |                |
   |                       | +--------------- ONE TRANSACTION --------+ |                |
   |                       | | uploads.complete       pending->completed               |
   |                       | | songs.insert           source_* from HEAD               |
   |                       | | uploads.claim_for_song uploads_claim_key                |
   |                       | | queue.enqueue        -> analysis_jobs = 'queued'        |
   |                       | +-----------------------------------------+ |                |
   |                       |------------------------>|                  |                |
   | 5  201 {upload, song, job{status:"queued"}}      |                  |                |
   |<----------------------|                         |                  |                |
   | 6  router.refresh()   |                         |                  |                |
   |    GET /songs (server-rendered list + job status)|                  |                |
   |---------------------->|  songs + active jobs    |                  |                |
   |                       |------------------------>|                  |                |
   |                       |                         |  claim_next (FOR UPDATE SKIP LOCKED)
   |                       |                         |<-------------------------------|
   | 7  GET /jobs/{id} -> queued | dispatched | running | succeeded | failed             |
```

Why each step is where it is:

1. **The `uploads` row is written before the URL is returned.** The presigner
   never invents a key; it renders one from an authorized row, so the key is
   `users/<uid>/uploads/<upload id>/<filename>` and nothing else. An attempt that
   is never completed stays visible to the sweeper.
2. **The browser holds the URL, not the credentials.** A presigned PUT is
   scoped to one key, one method, one `Content-Type` and one expiry - no R2 key
   ever reaches the browser, and R2 never sees a Supabase token.
3. **`complete` re-derives the facts.** The client's `declared_*` values are what
   it asked for; `bytes_actual`, `content_type_actual` and `etag_actual` come from
   `HEAD`. The size cap and the mp3/wav rule are enforced again against the
   object, so a client cannot lie about either.
4. **One transaction.** Upload, song, claim and job commit together or not at
   all: there is no song without a job, and no claimed upload without a song.

## Endpoints

All of them require `Authorization: Bearer <supabase access token>`, and every
query behind them is scoped by that token's `sub`. Unknown ids and someone else's
ids both answer `404`, so the API never confirms that another account's row
exists.

| Method | Path                | Request                                               | Response                                               |
| ------ | ------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| POST   | `/uploads/presign`  | `{filename, content_type?, bytes?, checksum_sha256?}` | `201 {upload, upload_url, method, headers, max_bytes}` |
| POST   | `/uploads/complete` | `{upload_id, title?, artist?, project_id?}`           | `201` (or `200` on a replay) `{upload, song, job}`     |
| GET    | `/uploads/{id}`     | -                                                     | `200 {upload}`                                         |
| GET    | `/songs/{id}`       | -                                                     | `200 {song, job}`                                      |
| GET    | `/songs`            | `?limit=`                                             | `200 {songs: [{...song, job}]}`                        |
| GET    | `/songs/{id}/midi`  | -                                                     | `200 {url, expires_at}`                                |
| GET    | `/songs/{id}/chords`| -                                                     | `200 {detector, vocabulary, key, hop_ms, summary, segments}` |
| GET    | `/jobs/{id}`        | -                                                     | `200 {job}`                                            |
| GET    | `/health`           | -                                                     | `200 {status}`                                         |

Upload rules: extension `mp3` or `wav`, MIME from that extension's alias set
(browsers report `audio/x-wav` and friends for WAV), at most 200 MiB
(`200 * 1024 * 1024`), checked against `declared_bytes` at presign and against the
object itself at complete.

Errors are one shape - `{"detail": {"code": "...", "message": "..."}}` - including
FastAPI's own request-validation failures:

| Status | Code                                                                       | When                                              |
| ------ | -------------------------------------------------------------------------- | ------------------------------------------------- |
| 401    | `unauthenticated`                                                          | missing, malformed, expired or unverifiable token |
| 422    | `invalid_request`, `invalid_filename`                                      | body or filename cannot be accepted               |
| 413    | `file_too_large`                                                           | declared or actual size over 200 MiB              |
| 415    | `unsupported_media_type`                                                   | not mp3/wav, by extension or by actual MIME       |
| 404    | `upload_not_found`, `song_not_found`, `job_not_found`, `project_not_found`, `analysis_not_ready` | unknown, not the caller's, or nothing to hand over yet |
| 409    | `upload_not_pending`, `object_not_found`, `object_empty`                   | wrong state, or the PUT never happened            |
| 410    | `upload_expired`                                                           | `expires_at` has passed                           |
| 503    | `storage_unavailable`, `auth_unavailable`                                  | R2 or the JWKS endpoint is unreachable            |
| 500    | `server_misconfigured`                                                     | a required setting is missing                     |

## Getting the MIDI back

The same flow, in the other direction, and deliberately the same shape: the artifact is
private, so the browser never learns its key and the API is only ever asked for a link.

```text
Browser                FastAPI                   Postgres          Cloudflare R2
   | 1  GET /songs/{id}/midi                                             |
   |---------------------->|                         |                  |
   |                       | song by id, scoped to the token's sub      |
   |                       |------------------------>|                  |
   |                       | songs.latest_job_id -> analysis_results    |
   |                       |                       (kind = 'midi')     |
   | 2  200 {url, expires_at}                        |                  |
   |<----------------------|                         |                  |
   | 3  navigate to <url>                                               |
   |------------------------------------------------------------------->|
   |<--------- 200 MIDI + Content-Disposition: attachment; filename=... -|
```

What each step is for:

1. **One object, named by a row.** The key comes from the job's `midi` artifact, never
   from the request, so a caller cannot name an object at all. The ownership check is the
   one `GET /songs/{id}` does: unknown ids, another account's ids and soft-deleted songs
   are all `404`.
2. **A link, not the bytes - and not a redirect.** The signed URL is scoped to one key,
   one method and an expiry (`MYBAND_DOWNLOAD_URL_TTL_SECONDS`, default 300 - much
   shorter than the upload's, because the link only has to survive the click that follows
   the response and the URL *is* the credential). A `302` would be followed by the
   `fetch`, which would leave the client holding the MIDI in memory instead of the user
   holding a file.
3. **The bucket names the file.** `ResponseContentDisposition` is part of the signature,
   so the object arrives as `attachment; filename="<title>.mid"`. An anchor's `download`
   attribute is ignored for a cross-origin URL, and this URL is always another origin, so
   the header is the only place that can say it. The title is user input, so it is
   sanitised to the object key's own alphabet before it becomes a header.
4. **Every other outcome is a `404`.** No finished job, or a finished job that stored no
   MIDI, are both `analysis_not_ready` - the message distinguishes "not analysed yet"
   from "produced no MIDI file", and nothing else does. The screen already shows the
   job's status, and there is nothing to download either way.

## Reading the chords back

Same route shape, one deliberate difference: the API reads the object and answers with the
timeline, because this is a screen's read rather than a file to save.

```text
Browser                FastAPI                   Postgres          Cloudflare R2
   | 1  GET /songs/{id}/chords                                           |
   |---------------------->|                         |                  |
   |                       | song by id, scoped to the token's sub      |
   |                       |------------------------>|                  |
   |                       | songs.latest_job_id -> analysis_results    |
   |                       |                       (kind = 'chords')   |
   |                       |------------------------>|                  |
   |                       | GET <object_key>                           |
   |                       |------------------------------------------->|
   |                       |<---------- chords.json (the whole timeline)-|
   | 2  200 {detector, vocabulary, key, hop_ms, summary, segments}       |
   |<----------------------|                         |                  |
```

1. **One object, named by a row.** As with the MIDI, the key comes from the job's
   `chords` artifact rather than from the request, and the ownership check is the one
   `GET /songs/{id}` does - unknown ids, another account's ids and soft-deleted songs
   are all `404`.
2. **The timeline, not a link to it.** A presigned URL would cost a second round trip
   (the API to sign, the browser to fetch) and hand the tab a link that expires while it
   is still on screen. The object is a few tens of kilobytes of JSON, so signing it would
   buy nothing that reading it does not.
3. **`summary` is the row's own digest, passed through unchanged.** The row is the
   authority on it, so a screen that only needs "what is this song made of" never has to
   fetch the timeline at all - and a timeline written before a digest field existed still
   answers.
4. **Every refusal is a `404` carrying `analysis_not_ready`.** The message is what
   separates the three: not analysed yet, analysed with no chords, or the timeline
   missing from the bucket. The seed's *Midnight Drive* row is the third case in
   practice - a demo fixture whose object was never uploaded - and it is answered rather
   than crashed on.

The response contract is mirrored in `packages/shared/src/analysis.ts`, which also carries
`segmentSchema`: the same four fields (`start_ms`, `end_ms`, `chord`, `confidence`) a
section list will use, so one renderer serves both.

## Watching a job finish

The dashboard renders the library on the server, in the request that asked for it, so the
list is a snapshot: right when it was drawn, wrong the moment a worker finishes. Nothing
pushes - there is no websocket and no SSE, and neither is worth standing up for four short
states, one of which a user usually sees for a second. So while any song in the list has a
job in `queued`, `dispatched` or `running`, the page re-runs its own Server Component every
five seconds (`features/uploads/components/library-refresh.tsx`). That is the same
`GET /songs` the page already made, and the same `router.refresh()` the uploader calls when
it has queued a job: no subscription, no second source of truth, nothing held in the tab.

It stops on its own, and it is the API's answer that stops it. The first refresh that comes
back with nothing in flight ends the polling, because that is the state being shown rather
than a stopwatch kept in the browser; a hidden tab skips its refresh; and after fifteen
minutes - the worker's own job timeout, and the lease the sweep uses - it stops asking and
offers a button instead. Work still unfinished after that is a question for
`GET /admin/metrics` and the queries in [queue-state-machine.md](queue-state-machine.md),
not one the page can answer.

`features/uploads/jobs.ts` is where "in flight" is defined for the browser. It mirrors
`analysis_job.ACTIVE_STATUSES`, and it is a plain module rather than part of the poller so
that the dashboard - a Server Component - can decide with the same answer.

## Invariants this flow keeps

- `uploads.object_key` is `users/<uid>/uploads/<upload id>/<filename>`, derived
  from the authenticated user - never from the request body alone.
- `uploads.status` moves `pending -> completed` by compare-and-swap on `pending`,
  so concurrent completes cannot both win.
- A completed upload always carries `bytes_actual` and `completed_at`
  (`uploads_completed_check`), taken from the object rather than from the client.
- One song per upload (`uploads_claim_key`) and one job in flight per song
  (`analysis_jobs_one_active_per_song_key`) are enforced by the database, not by a
  read-then-write in the API.
- `songs.source_object_key` is immutable: a re-upload is a new upload row and a
  new song.
- The API never sees an audio byte. It signs a URL and afterwards confirms what
  landed; the object's size and MIME are the bucket's answer, not the browser's.
- A download link is built from rows the caller owns, not from the request: the key
  comes from the job's artifact, the expiry from configuration, and the filename from
  the song's title. No route takes an object key from a browser in either direction.

## Running it locally

FastAPI needs a migrated database and somewhere to put audio. `supabase start`
provides all of it - Postgres, Auth, and an S3-compatible storage endpoint:

```bash
pnpm dlx supabase@latest start     # prints the storage endpoint, keys and region
pnpm dev:api                       # http://127.0.0.1:8000
pnpm dev:web                       # http://localhost:3000
```

`supabase start` prints an S3 section, and the API can be pointed at it verbatim:

```ini
R2_ACCOUNT_ID=local
R2_ENDPOINT_URL=http://127.0.0.1:54321/storage/v1/s3
R2_ACCESS_KEY_ID=<the access key it printed>
R2_SECRET_ACCESS_KEY=<the secret key it printed>
R2_REGION=local
R2_BUCKET=myband-audio
```

The bucket has to exist before the first presign, because the presigned PUT is the
only thing that creates an object:

```sql
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('myband-audio', 'myband-audio', false, 209715200,
        array['audio/mpeg', 'audio/wav', 'audio/midi', 'application/json'])
on conflict (id) do update
    set allowed_mime_types = excluded.allowed_mime_types,
        file_size_limit = excluded.file_size_limit;
```

The last two are there for the analysis worker, not for the browser: both of its artifacts are
written into the same bucket, and a storage policy is enforced on every PUT - including the ones
the API never sees. `audio/midi` is the MIDI file and `application/json` the chord timeline.
Leaving either out produces a 415 on the worker's write, which surfaces as `storage_rejected` on
the job at whichever `store_*` stage writes it (see docs/analysis-worker.md). A new artifact kind
means a new content type in this list, and nothing on the API side can tell you it is missing.

With a real Cloudflare R2 bucket, the same code runs unchanged: drop `R2_ENDPOINT_URL`
and `R2_REGION` and set `R2_ACCOUNT_ID` to the account id. What the bucket itself has to
be configured with is the next section.

## Required bucket configuration

Three things have to be right before the first presign, in whichever bucket a deployment
uses. All three are enforced by the *bucket*, which is the point: the API signs the PUT,
but the write is the bucket's to allow or refuse.

| Setting | Value | Why |
| --- | --- | --- |
| Allowed content types | `audio/mpeg`, `audio/wav`, **`audio/midi`**, **`application/json`** | the browser uploads the first two, the analysis worker writes the last two |
| Object size limit | at least the 200 MiB cap (`209715200`) | the cap is the API's rule; a stricter bucket limit refuses a legal upload with a 403 the user can do nothing about |
| CORS | `PUT` from the web origin, `Content-Type` allowed | the upload goes from the browser straight to the bucket, with no API in the path |

### Supabase Storage and Cloudflare R2 are not the same shape

Worth knowing before a deploy, because only one of them can refuse a write:

- **Supabase Storage** enforces `allowed_mime_types` and `file_size_limit` on every
  upload, and compares `allowed_mime_types` against the `Content-Type` of the PUT - which
  is the type the API signed. That is what `upload_rules.resolve_content_type` is for:
  a WAV declared as `audio/x-wav` or `audio/wave` is signed as `audio/wav`, so the bucket
  never sees an alias it does not have in its list. The list above still has to contain the
  canonical types, and both worker types still have to be in it - `audio/midi` for the MIDI,
  `application/json` for the chord timeline.
- **Cloudflare R2 has no equivalent.** There is no `allowed_mime_types` and no per-bucket
  size limit to set: the only gates are the presigned URL's own scope and the API's checks
  (`check_object`, `resolve_content_type`), so the code is the single source of truth for
  what may be uploaded. The flip side is that nothing else can silently start refusing the
  worker's MIDI write, and nothing else protects the bucket either - a lifecycle rule is
  the backstop for a stray object.

The local `supabase start` stack is Supabase Storage, which is why
`docs/analysis-worker.md` has a paragraph about the 415 the worker got from a bucket
created without `audio/midi`: it is the one upload failure only the bucket can produce.


## Deliberately not here yet

- **A sweeper for abandoned uploads.** `uploads.list_pending_expired` and
  `storage_gc_queue` exist for it; until it runs, an abandoned `pending` row stays
  pending and its object was never uploaded - one row, no storage.
- **A producer and a drainer for `storage_gc_queue`.** The table, its indexes and its
  model (`app/models/storage_gc.py`: enqueue, list_due, complete, retry) are all in place,
  and nothing calls any of them. Nothing enqueues an object when its row is hard deleted,
  and nothing drains the queue - so **a hard-deleted song's audio stays in the bucket
  forever**, silently. It is a cost and retention item rather than a correctness one: once
  the `songs` row is gone, no row references the object, so nothing can serve it. The
  design intent is that the object is only ever *owed* a delete (enqueued in the same
  transaction that removes the row, so a failing S3 call cannot roll back a user action),
  which is why this is a missing worker rather than a missing mechanism. Tracked as R4 in
  the risk register (`PRODUCTION_READINESS.md`).
- **Checksum verification.** `checksum_expected` is recorded from the presign
  request; verifying it needs the PUT to be signed with `x-amz-checksum-sha256`,
  which presigning alone cannot arrange, so the column is filled and trusted for
  now.
- **A bucket-side maximum size.** The 200 MiB cap is enforced before a song is
  created, so an oversized object is uploaded but never referenced. An R2
  lifecycle rule is the backstop.
- **The dispatcher.** Jobs stay `queued` until the RunPod worker loop lands; the
  queue service it will call is already written and tested
  (`app/services/queue.py`). Nothing reads RunPod today, so production is not asked
  for its credentials (`app/core/config.py`, `_require_production_secrets`); the
  commit that adds the dispatcher should put them back in that map.
- **A download for anything but the MIDI.** `analysis_results` holds `bpm`, `key`
  and `chords` rows, and only `chords` has a route of its own
  (`GET /songs/{id}/chords`, read by the song page); tempo and key are read from
  the `songs` row's headline columns. The signing is general - `presign_get` takes
  any key - so each is a route and a schema away rather than a piece of machinery.
- **Ranged or streamed reads.** A link fetches the whole object. Playing the
  recording in a `<audio>` element from the bucket would want a range-capable URL and
  an expiry sized for a listening session, not for the click that follows a response.
