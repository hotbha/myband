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
| 404    | `upload_not_found`, `song_not_found`, `job_not_found`, `project_not_found` | unknown, or not the caller's                      |
| 409    | `upload_not_pending`, `object_not_found`, `object_empty`                   | wrong state, or the PUT never happened            |
| 410    | `upload_expired`                                                           | `expires_at` has passed                           |
| 503    | `storage_unavailable`, `auth_unavailable`                                  | R2 or the JWKS endpoint is unreachable            |
| 500    | `server_misconfigured`                                                     | a required setting is missing                     |

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
        array['audio/mpeg', 'audio/wav', 'audio/midi'])
on conflict (id) do update
    set allowed_mime_types = excluded.allowed_mime_types,
        file_size_limit = excluded.file_size_limit;
```

`audio/midi` is there for the analysis worker, not for the browser: its MIDI artifact is
written into the same bucket, and a storage policy is enforced on every PUT - including
the ones the API never sees. Leaving it out produces a 415 on the worker's write, which
surfaces as `storage_rejected` on the job (see docs/analysis-worker.md).

With a real Cloudflare R2 bucket, the same code runs unchanged: drop
`R2_ENDPOINT_URL` and `R2_REGION`, set `R2_ACCOUNT_ID` to the account id, and add a
bucket CORS rule allowing `PUT` from the web origin with the `Content-Type` header.

## Deliberately not here yet

- **A sweeper for abandoned uploads.** `uploads.list_pending_expired` and
  `storage_gc_queue` exist for it; until it runs, an abandoned `pending` row stays
  pending and its object was never uploaded - one row, no storage.
- **Checksum verification.** `checksum_expected` is recorded from the presign
  request; verifying it needs the PUT to be signed with `x-amz-checksum-sha256`,
  which presigning alone cannot arrange, so the column is filled and trusted for
  now.
- **A bucket-side maximum size.** The 200 MiB cap is enforced before a song is
  created, so an oversized object is uploaded but never referenced. An R2
  lifecycle rule is the backstop.
- **The dispatcher.** Jobs stay `queued` until the RunPod worker loop lands; the
  queue service it will call is already written and tested
  (`app/services/queue.py`).
