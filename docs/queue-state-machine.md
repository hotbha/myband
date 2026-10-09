# The analysis queue's state machine

`public.analysis_jobs.status` is the whole protocol. One row is one attempt at
analysing one song, and every move a row makes is made by `app/services/queue.py`,
which is the only module that writes the column.

```
                     claim_next            worker starts            worker finishes
   queued  ────────────────────>  dispatched  ──────────>  running  ────────────────>  succeeded
     │                                │                      │
     │  (never expires)               └──────┬───────────────┘
     │                                       │ sweep: no heartbeat for 15 minutes
     │                                       ▼
     │                                     failed
     └── a retry is a *new row*: nothing ever moves a job back to queued

   failed / canceled are terminal, and so is succeeded: no statement in the codebase
   can move a job out of a terminal status, which is what makes usage countable.
```

## Who writes what

| Status       | Moved there by                          | Means to the user                                     |
| ------------ | --------------------------------------- | ----------------------------------------------------- |
| `queued`     | `queue.enqueue`                         | "Waiting." Nothing is running yet.                     |
| `dispatched` | `queue.mark_dispatched`                 | "Starting a worker." A GPU has been handed the job.    |
| `running`    | `queue.begin` / `queue.mark_running`    | "Analysing." The worker is heartbeating.               |
| `succeeded`  | `queue.complete`                        | "Done." Results and `songs.latest_job_id` are written. |
| `failed`     | `queue.fail`, `queue.reap_stale`        | "Could not analyse this." `error_code` says why.       |
| `canceled`   | nothing yet (see _Deliberately absent_) | Not reachable in the product today.                    |

`queue.begin` is the self-hosted path - `queued` straight to `running`, with no
dispatch hop - and it is the one the RunPod worker loop uses. `mark_dispatched`
exists for the case where something else owns the GPU lifecycle.

## The two clocks

Only one of the two in-flight states is on a timer, and that asymmetry is the point.

- **`queued` has no clock.** A queued job is waiting for a _dispatcher_, not for a
  worker, so silence from it is not evidence that anything went wrong. It is
  therefore never reaped, however old it is: an undrained backlog shows up as a
  growing `queued` count, which is a fact about the deployment and not a reason to
  fail work nobody ever started.
- **`dispatched` and `running` are on a heartbeat lease.** A worker reports with
  `queue.heartbeat` every 15 seconds; a job whose last sign of life
  (`heartbeat_at`, falling back to `started_at`, `dispatched_at`, `created_at`) is
  more than `queue.STALE_AFTER` (15 minutes) old is assumed dead and reaped. Several
  missed beats are expected to be harmless, so the lease is far wider than the
  interval.

`analysis_job.HEARTBEAT_STATUSES` is the tuple that encodes this - the sweep's
candidate set - and `analysis_job.ACTIVE_STATUSES` (which also includes `queued`) is
what "in flight" means to everything else: the one-job-per-song index, the library's
status lookup, and the dashboard.

## Invariants

- **One job in flight per song.** The partial unique index
  `analysis_jobs_one_active_per_song_key` refuses a second `queued`/`dispatched`/
  `running` row for a song, so a double click cannot start two analyses. The API
  reports the second request as the job already in flight.
- **Every transition is a compare-and-swap.** The guard is the status the caller
  _believed_ the row was in, so a worker whose job was reaped, canceled or finished
  by someone else gets `None` back and stops instead of overwriting the winner.
- **A retry is a new row.** Nothing resurrects a terminal job, which keeps
  `attempts` and the usage meter honest.
- **Terminal means finished.** `finished_at is not null` is equivalent to being
  terminal, enforced in both directions by a `CHECK`; `failed` always carries an
  `error_code`.
- **The reaper fails, it does not requeue.** Starting a second attempt behind a
  user's back is a product decision, not something a background sweep makes.

## What the sweep may touch

`queue.reap_stale` is deliberately narrow:

| Status                              | Reaped for age? | Why                                                      |
| ----------------------------------- | --------------- | -------------------------------------------------------- |
| `queued`                            | **no**          | Nobody was handed it, so there is nothing to be silent.  |
| `dispatched` / `running`            | yes, after 15m  | A worker is supposed to be reporting; it stopped.        |
| `succeeded` / `failed` / `canceled` | **no**          | Terminal. The `transition` guard refuses to leave these. |

A reaped job is a `failed` job with `error_code = 'stale'`, so it is never billable
and a user-visible retry queues a new row.

## Deliberately absent

- **No cancel path.** There is no `queue.cancel` and no route that writes
  `canceled`: the status exists in the schema, the API contract accepts it, and
  `queue.reap_stale` would leave such a row alone, but nothing produces one yet.
  Adding it is a product decision (and a route), not a queue mechanism.
- **No priorities and no scheduling.** The queue is `order by created_at`, and
  `claim_next` locks with `FOR UPDATE SKIP LOCKED` so two dispatchers never hand the
  same job to two workers. There is no broker, and no reordering.
- **No requeue of a terminal job.** A retry is a new row, always.

## Operating the queue

The three questions worth asking of production, answered directly:

```sql
-- Is anything stuck in flight past its lease?
select status, count(*)
from public.analysis_jobs
where status in ('dispatched', 'running') and deleted_at is null
group by status;

-- Is the dispatcher keeping up? (age of the oldest queued job)
select now() - min(created_at) as oldest_queued
from public.analysis_jobs
where status = 'queued' and deleted_at is null;

-- What did this song actually do, over time?
select status, created_at, finished_at, error_code
from public.analysis_jobs
where song_id = $1 and deleted_at is null
order by created_at desc;
```

The same grouped counts, and the ages that go with them, are exposed by
`GET /admin/metrics` (see `app/api/routes/metrics.py`; the token is
`MYBAND_METRICS_TOKEN`). [schema.md](schema.md) has the columns, and
[analysis-worker.md](analysis-worker.md) has what the worker does with a job it holds.

