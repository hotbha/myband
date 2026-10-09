"""Data access for ``public.storage_gc_queue``.

The work list of objects R2 still owes a delete (or a multipart abort). Rows are
enqueued in the same transaction that removes the row owning the object, so a
failing S3 call can never roll back a user action, and drained by a worker that
claims due rows and reports the outcome back here.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record

MAX_LAST_ERROR_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class StorageGcEntry(Record):
    id: UUID
    user_id: UUID | None
    object_key: str
    operation: str
    multipart_upload_id: str | None
    reason: str
    attempts: int
    last_error: str | None
    enqueued_at: datetime
    next_attempt_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None


def enqueue(
    conn: psycopg.Connection,
    *,
    object_key: str,
    reason: str,
    operation: str = "delete_object",
    multipart_upload_id: str | None = None,
    user_id: UUID | None = None,
    gc_id: UUID | None = None,
) -> StorageGcEntry:
    """Queue an object for cleanup, reopening the row if it was already done.

    ``unique(object_key)`` makes this idempotent: re-enqueueing resets the attempt
    count and clears the completion instead of inserting a second row for the same
    object. The stored ``user_id`` is kept when the caller does not know it, so the
    audit trail survives an account deletion.
    """
    row = conn.execute(
        """
        insert into public.storage_gc_queue (
            id, user_id, object_key, operation, multipart_upload_id, reason
        )
        values (%s, %s, %s, %s, %s, %s)
        on conflict (object_key) do update set
            operation = excluded.operation,
            multipart_upload_id = excluded.multipart_upload_id,
            reason = excluded.reason,
            user_id = coalesce(excluded.user_id, storage_gc_queue.user_id),
            attempts = 0,
            last_error = null,
            next_attempt_at = now(),
            claimed_at = null,
            completed_at = null
        returning *
        """,
        (
            gc_id or new_id(),
            user_id,
            object_key,
            operation,
            multipart_upload_id,
            reason,
        ),
    ).fetchone()
    return StorageGcEntry.from_row(row)


def list_due(
    conn: psycopg.Connection,
    *,
    limit: int = 100,
    claim_at: datetime | None = None,
) -> list[StorageGcEntry]:
    """Unfinished entries whose next attempt is due, oldest first.

    ``FOR UPDATE SKIP LOCKED`` so several workers can drain the queue at once.
    Supported by ``storage_gc_queue_due_idx``.
    """
    rows = conn.execute(
        """
        select *
        from public.storage_gc_queue
        where completed_at is null and next_attempt_at <= now()
        order by next_attempt_at
        limit %s
        for update skip locked
        """,
        (limit,),
    ).fetchall()
    entries = [StorageGcEntry.from_row(row) for row in rows]
    if claim_at is not None and entries:
        conn.execute(
            """
            update public.storage_gc_queue
            set claimed_at = %s
            where id = any(%s)
            """,
            (claim_at, [entry.id for entry in entries]),
        )
    return entries


def complete(conn: psycopg.Connection, *, gc_id: UUID) -> bool:
    """Mark an entry done. ``False`` when it was already done or never existed."""
    row = conn.execute(
        """
        update public.storage_gc_queue
        set completed_at = now(), last_error = null
        where id = %s and completed_at is null
        returning id
        """,
        (gc_id,),
    ).fetchone()
    return row is not None


def retry(
    conn: psycopg.Connection,
    *,
    gc_id: UUID,
    error: str,
    next_attempt_at: datetime,
) -> bool:
    """Record a failed attempt and schedule the next one.

    The error text is truncated to the column's CHECK, because a provider message
    that is one character too long should not cost us the attempt count.
    """
    row = conn.execute(
        """
        update public.storage_gc_queue
        set attempts = attempts + 1,
            last_error = %s,
            next_attempt_at = %s,
            claimed_at = null
        where id = %s and completed_at is null
        returning id
        """,
        (error[:MAX_LAST_ERROR_LENGTH], next_attempt_at, gc_id),
    ).fetchone()
    return row is not None
