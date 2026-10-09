"""Data access for ``public.analysis_jobs``.

The row is the queue entry: ``status`` is the whole protocol, and the partial
unique index ``analysis_jobs_one_active_per_song_key`` - not this module - is what
guarantees a song has at most one job in flight. Statements here never commit;
the queue service owns the transaction boundary.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record

# Kept in step with the CHECK constraint on the column.
ACTIVE_STATUSES = ("queued", "dispatched", "running")
TERMINAL_STATUSES = ("succeeded", "failed", "canceled")

# The active statuses as SQL text, for the partial-index inference in `insert`
# and for the `in (...)` lists below. Literal on purpose: an ON CONFLICT
# inference clause only matches the partial index when the predicate is the same.
_STATUS_LIST = "'queued', 'dispatched', 'running'"

# Terminal statuses. Nothing moves a job out of these - a retry is a new row -
# and `transition` refuses to even try, so a late worker cannot resurrect one.
_TERMINAL_LIST = "'succeeded', 'failed', 'canceled'"

# Columns `transition` may write. These names are interpolated into SQL, so they
# come from this set and never from the caller.
_TRANSITION_COLUMNS = frozenset(
    {
        "attempts",
        "compute_seconds",
        "dispatched_at",
        "error_code",
        "error_message",
        "finished_at",
        "heartbeat_at",
        "runpod_job_id",
        "started_at",
    }
)


@dataclass(frozen=True, slots=True)
class AnalysisJob(Record):
    id: UUID
    user_id: UUID
    song_id: UUID
    status: str
    pipeline_version: str
    source_object_key: str
    source_checksum: str | None
    attempts: int
    compute_seconds: Decimal | None
    runpod_job_id: str | None
    error_code: str | None
    error_message: str | None
    dispatched_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def insert(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    pipeline_version: str,
    source_object_key: str,
    source_checksum: str | None = None,
    job_id: UUID | None = None,
) -> AnalysisJob | None:
    """Queue a job, unless the song already has one in flight.

    ``None`` means the partial unique index refused the row - the double-click
    case - and the caller should keep the job that is already there.
    """
    row = conn.execute(
        f"""
        insert into public.analysis_jobs (
            id, user_id, song_id, pipeline_version, source_object_key, source_checksum
        )
        values (%s, %s, %s, %s, %s, %s)
        on conflict (song_id) where status in ({_STATUS_LIST}) do nothing
        returning *
        """,
        (
            job_id or new_id(),
            user_id,
            song_id,
            pipeline_version,
            source_object_key,
            source_checksum,
        ),
    ).fetchone()
    return None if row is None else AnalysisJob.from_row(row)


def get(conn: psycopg.Connection, job_id: UUID) -> AnalysisJob | None:
    """Fetch one job, deleted or not."""
    row = conn.execute(
        "select * from public.analysis_jobs where id = %s",
        (job_id,),
    ).fetchone()
    return None if row is None else AnalysisJob.from_row(row)


def get_active_for_song(conn: psycopg.Connection, song_id: UUID) -> AnalysisJob | None:
    """The song's in-flight job, if it has one.

    ``analysis_jobs_one_active_per_song_key`` makes this at most one row, so the
    ordering is only a tie-breaker for a row that is uncommitted, not a choice
    between several.
    """
    row = conn.execute(
        f"""
        select *
        from public.analysis_jobs
        where song_id = %s and status in ({_STATUS_LIST}) and deleted_at is null
        order by created_at desc
        limit 1
        """,
        (song_id,),
    ).fetchone()
    return None if row is None else AnalysisJob.from_row(row)


def list_for_song(
    conn: psycopg.Connection,
    song_id: UUID,
    *,
    limit: int = 20,
) -> list[AnalysisJob]:
    """A song's job history, newest first. Retries appear as separate rows."""
    rows = conn.execute(
        """
        select *
        from public.analysis_jobs
        where song_id = %s
        order by created_at desc
        limit %s
        """,
        (song_id, limit),
    ).fetchall()
    return [AnalysisJob.from_row(row) for row in rows]


def list_active_for_songs(
    conn: psycopg.Connection,
    song_ids: Sequence[UUID],
) -> list[AnalysisJob]:
    """The in-flight jobs of several songs, in one query.

    The library list needs a status per song, and asking per song would be one
    round trip per row. At most one job per song can match, because
    ``analysis_jobs_one_active_per_song_key`` allows only one at a time.
    """
    if not song_ids:
        return []

    rows = conn.execute(
        f"""
        select *
        from public.analysis_jobs
        where song_id = any(%s) and status in ({_STATUS_LIST}) and deleted_at is null
        """,
        (list(song_ids),),
    ).fetchall()
    return [AnalysisJob.from_row(row) for row in rows]


def claim_next_queued(
    conn: psycopg.Connection,
    *,
    limit: int = 1,
) -> list[AnalysisJob]:
    """Lock the oldest queued jobs and return them.

    ``FOR UPDATE SKIP LOCKED`` is what makes two dispatchers safe: each takes rows
    nobody else holds instead of waiting behind them. The lock lasts until the
    transaction ends, so the caller has to mark the rows dispatched and commit in
    the same transaction, or the claim is lost when it rolls back.
    """
    rows = conn.execute(
        """
        select *
        from public.analysis_jobs
        where status = 'queued' and deleted_at is null
        order by created_at
        limit %s
        for update skip locked
        """,
        (limit,),
    ).fetchall()
    return [AnalysisJob.from_row(row) for row in rows]


def list_stale_active(
    conn: psycopg.Connection,
    *,
    before: datetime,
    limit: int = 100,
) -> list[AnalysisJob]:
    """In-flight jobs whose last sign of life is older than ``before``.

    A job that was dispatched but never heartbeated falls back to its dispatch
    time, so a worker that dies on arrival is reaped like any other. The scan is
    supported by the active-set index and bounded by worker concurrency.
    """
    rows = conn.execute(
        f"""
        select *
        from public.analysis_jobs
        where status in ({_STATUS_LIST})
          and coalesce(heartbeat_at, started_at, dispatched_at, created_at) < %s
        order by created_at
        limit %s
        """,
        (before, limit),
    ).fetchall()
    return [AnalysisJob.from_row(row) for row in rows]


def touch_heartbeat(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    at: datetime,
) -> bool:
    """Stamp ``heartbeat_at`` on a job that is still in flight.

    ``False`` means the job moved on - finished, failed or reaped - and the worker
    holding it should stop, because it no longer owns the row.
    """
    row = conn.execute(
        f"""
        update public.analysis_jobs
        set heartbeat_at = %s
        where id = %s and status in ({_STATUS_LIST})
        returning id
        """,
        (at, job_id),
    ).fetchone()
    return row is not None


def transition(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    expected_status: str,
    status: str,
    **fields: Any,
) -> AnalysisJob | None:
    """Move a job from ``expected_status`` to ``status``, or return ``None``.

    The guard is the row's own current status, so a transition is a
    compare-and-swap: whoever gets there first wins, everyone else is told no and
    should not touch the job again. A terminal job is final - the guard also
    refuses to leave ``succeeded``, ``failed`` or ``canceled``, which is what makes
    "a retry is a new row" a property of the data rather than a convention.

    Extra keyword arguments are written in the same statement (``finished_at``,
    ``error_code``, ...) and are restricted to ``_TRANSITION_COLUMNS``, because the
    names become part of the SQL.
    """
    unknown = set(fields) - _TRANSITION_COLUMNS
    if unknown:
        raise ValueError(f"not a writable analysis_jobs column: {sorted(unknown)}")

    assignments = ["status = %s"]
    params: list[Any] = [status]
    for column, value in fields.items():
        assignments.append(f"{column} = %s")
        params.append(value)
    params.extend((job_id, expected_status))

    row = conn.execute(
        f"""
        update public.analysis_jobs
        set {", ".join(assignments)}
        where id = %s
          and status = %s
          and status not in ({_TERMINAL_LIST})
        returning *
        """,
        params,
    ).fetchone()
    return None if row is None else AnalysisJob.from_row(row)
