"""The analysis queue.

One row per attempt, and this module is the only thing that moves one between
states::

    queued -> dispatched -> running -> succeeded | failed | canceled

Decisions worth knowing before changing anything here:

* A dispatcher claims work with :func:`claim_next`, which locks rows using
  ``FOR UPDATE SKIP LOCKED``. That is the entire concurrency story: no broker, no
  advisory locks, and no double dispatch when two dispatchers run side by side.
* Every transition is guarded by the status the caller *believed* the job was in,
  so a worker whose job was reaped or canceled finds out, instead of overwriting
  whoever holds it now.
* Nothing here commits. The caller wraps a unit of work in one transaction, which
  is what makes :func:`complete` atomic with the song pointer it updates, and what
  keeps the row lock in :func:`claim_next` alive until the job is dispatched.
* Lifecycle timestamps come from the caller rather than from ``now()``: the worker
  owns its own clock, and a slow HTTP hop should not distort ``compute_seconds``.
  ``created_at`` and ``updated_at`` stay the database's.
* A retry is a new job row. Nothing resurrects a terminal job, which is what makes
  usage countable: one billable unit is one job that reached ``succeeded`` (see
  docs/schema.md, "Billable unit").

Deliberately not here: the dispatcher loop, the RunPod client and the HTTP routes.
This module is the seam they will call.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from app.models import analysis_job, analysis_result, song
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import ResultInput

# A job nobody has heard from for this long is assumed dead. The worker
# heartbeats well inside the window, including while it waits on RunPod.
STALE_AFTER = timedelta(minutes=15)

# Upper bound on any single claim or reap, so a caller cannot accidentally ask for
# the whole queue.
MAX_BATCH = 100


@dataclass(frozen=True, slots=True)
class EnqueueOutcome:
    """What :func:`enqueue` did.

    ``created`` is ``False`` when the song already had a job in flight. ``job`` is
    that existing job when this transaction can see it - which it may not, if the
    competing insert has not committed yet - so a caller that needs certainty
    should re-read the song's state rather than treat ``None`` as "no job".
    """

    created: bool
    job: AnalysisJob | None


def enqueue(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    pipeline_version: str,
    source_object_key: str,
    source_checksum: str | None = None,
) -> EnqueueOutcome:
    """Queue an analysis for a song.

    Requeueing a song that already has work in flight returns that work instead of
    starting a second run. The partial unique index decides, not a read-then-write
    in this process, so two simultaneous requests cannot both queue a job.
    """
    created = analysis_job.insert(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=pipeline_version,
        source_object_key=source_object_key,
        source_checksum=source_checksum,
    )
    if created is not None:
        return EnqueueOutcome(created=True, job=created)
    existing = analysis_job.get_active_for_song(conn, song_id)
    return EnqueueOutcome(created=False, job=existing)


def claim_next(conn: psycopg.Connection, *, limit: int = 1) -> list[AnalysisJob]:
    """Lock up to ``limit`` queued jobs for dispatch, oldest first.

    The caller has to commit after marking them dispatched: the row lock taken
    here is what stops a second dispatcher from handing the same job to a second
    worker, and it disappears with the transaction.
    """
    return analysis_job.claim_next_queued(conn, limit=max(1, min(limit, MAX_BATCH)))


def mark_dispatched(
    conn: psycopg.Connection,
    *,
    job: AnalysisJob,
    runpod_job_id: str,
    at: datetime | None = None,
) -> AnalysisJob | None:
    """``queued`` -> ``dispatched``, once the worker knows about the job.

    Takes the claimed job rather than an id: you can only dispatch something you
    hold, and its status is the guard this transition is checked against. The
    attempt is counted here, so ``attempts`` means "times handed to a worker".
    """
    moment = at or _now()
    return analysis_job.transition(
        conn,
        job_id=job.id,
        expected_status=job.status,
        status="dispatched",
        attempts=job.attempts + 1,
        runpod_job_id=runpod_job_id,
        dispatched_at=moment,
        heartbeat_at=moment,
    )


def mark_running(
    conn: psycopg.Connection,
    *,
    job: AnalysisJob,
    at: datetime | None = None,
) -> AnalysisJob | None:
    """``dispatched`` -> ``running``, once the GPU has picked the work up.

    Returns ``None`` when the job is no longer in the state the caller assumed,
    which is the signal to stop working on it.
    """
    moment = at or _now()
    return analysis_job.transition(
        conn,
        job_id=job.id,
        expected_status=job.status,
        status="running",
        started_at=moment,
        heartbeat_at=moment,
    )


def heartbeat(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    at: datetime | None = None,
) -> bool:
    """Report that the worker is still alive.

    Only ``heartbeat_at`` is written, which is not indexed, so these statements
    stay eligible for HOT updates and do not bloat the queue's indexes. ``False``
    means the job is no longer in flight and the worker should abort.
    """
    return analysis_job.touch_heartbeat(conn, job_id=job_id, at=at or _now())


def complete(
    conn: psycopg.Connection,
    *,
    job: AnalysisJob,
    results: Sequence[ResultInput],
    compute_seconds: float | Decimal | None = None,
    at: datetime | None = None,
) -> AnalysisJob | None:
    """Finish a job successfully, storing its artifacts and the song pointer.

    Three writes in one transaction: the artifacts, the job row, and
    ``songs.latest_job_id``. Keeping them together is what stops the library from
    showing a finished job whose results are missing, and it is why this takes a
    connection the caller controls rather than opening its own.

    ``None`` means the job was no longer in the state the caller assumed - reaped,
    canceled or already finished. Nothing is written in that case, not even the
    artifacts, because they are only worth storing once the transition is won.
    """
    finished = analysis_job.transition(
        conn,
        job_id=job.id,
        expected_status=job.status,
        status="succeeded",
        finished_at=at or _now(),
        compute_seconds=compute_seconds,
        error_code=None,
        error_message=None,
    )
    if finished is None:
        return None
    analysis_result.upsert_many(conn, job_id=job.id, results=results)
    song.set_latest_job(conn, song_id=job.song_id, job_id=job.id)
    return finished


def fail(
    conn: psycopg.Connection,
    *,
    job: AnalysisJob,
    error_code: str,
    error_message: str | None = None,
    at: datetime | None = None,
) -> AnalysisJob | None:
    """Take a job to ``failed``.

    ``error_code`` is the short, stable string the product groups by
    (``decode_error``, ``worker_timeout``, ``stale``); the readable detail goes in
    ``error_message``. Both are truncated to fit their column CHECKs.

    Failed is terminal and never billable: a retry queues a new job.
    """
    return analysis_job.transition(
        conn,
        job_id=job.id,
        expected_status=job.status,
        status="failed",
        finished_at=at or _now(),
        error_code=error_code[:64],
        error_message=error_message[:2000] if error_message else None,
    )


def reap_stale(
    conn: psycopg.Connection,
    *,
    older_than: timedelta = STALE_AFTER,
    limit: int = MAX_BATCH,
    at: datetime | None = None,
) -> list[AnalysisJob]:
    """Fail in-flight jobs whose worker stopped reporting.

    A worker that is killed cannot report anything, so a sweep is the only way a
    job leaves ``dispatched``/``running``. Reaped jobs are marked failed rather
    than requeued: ``attempts`` already counts the try, and starting over is a
    product decision (a new job row), not something a background sweep should do
    behind the user's back.

    Each job is guarded by its own observed status, so one that finished while
    this ran is left alone and simply does not appear in the result.
    """
    now = at or _now()
    reaped: list[AnalysisJob] = []
    stale_jobs = analysis_job.list_stale_active(conn, before=now - older_than, limit=limit)
    for stale in stale_jobs:
        failed = analysis_job.transition(
            conn,
            job_id=stale.id,
            expected_status=stale.status,
            status="failed",
            finished_at=now,
            error_code="stale",
            error_message=(
                f"no heartbeat for {int(older_than.total_seconds())}s; the worker is assumed dead"
            ),
        )
        if failed is not None:
            reaped.append(failed)
    return reaped


def _now() -> datetime:
    """Current instant as an aware UTC datetime, which is what timestamptz wants."""
    return datetime.now(UTC)
