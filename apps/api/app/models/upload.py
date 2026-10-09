"""Data access for ``public.uploads``.

The browser uploads straight to R2, so this row is the API's account of what it
allowed: ``create_pending`` before the presigned PUT, ``complete`` when the object
is confirmed in the bucket, ``claim_for_song`` when it becomes a song, and
``list_pending_expired`` for the sweeper that reclaims abandoned attempts.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record


@dataclass(frozen=True, slots=True)
class Upload(Record):
    id: UUID
    user_id: UUID
    song_id: UUID | None
    object_key: str
    status: str
    declared_bytes: int | None
    declared_content_type: str | None
    checksum_expected: str | None
    bytes_actual: int | None
    content_type_actual: str | None
    checksum_actual: str | None
    etag_actual: str | None
    multipart_upload_id: str | None
    expires_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def create_pending(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    object_key: str,
    expires_at: datetime,
    declared_bytes: int | None = None,
    declared_content_type: str | None = None,
    checksum_expected: str | None = None,
    multipart_upload_id: str | None = None,
    upload_id: UUID | None = None,
) -> Upload:
    """Record an upload the API is about to presign."""
    row = conn.execute(
        """
        insert into public.uploads (
            id, user_id, object_key, expires_at, declared_bytes,
            declared_content_type, checksum_expected, multipart_upload_id
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            upload_id or new_id(),
            user_id,
            object_key,
            expires_at,
            declared_bytes,
            declared_content_type,
            checksum_expected,
            multipart_upload_id,
        ),
    ).fetchone()
    return Upload.from_row(row)


def get(conn: psycopg.Connection, upload_id: UUID) -> Upload | None:
    """Fetch one upload."""
    row = conn.execute(
        "select * from public.uploads where id = %s",
        (upload_id,),
    ).fetchone()
    return None if row is None else Upload.from_row(row)


def complete(
    conn: psycopg.Connection,
    *,
    upload_id: UUID,
    bytes_actual: int,
    completed_at: datetime,
    content_type_actual: str | None = None,
    checksum_actual: str | None = None,
    etag_actual: str | None = None,
) -> Upload | None:
    """Mark a pending upload completed, reporting what landed in the bucket.

    ``bytes_actual`` and ``completed_at`` are what the CHECK requires a completed
    upload to carry, so they are not optional here either. Returns ``None`` when
    the upload was already completed, aborted or expired.
    """
    row = conn.execute(
        """
        update public.uploads
        set status = 'completed',
            bytes_actual = %s,
            completed_at = %s,
            content_type_actual = %s,
            checksum_actual = %s,
            etag_actual = %s
        where id = %s and status = 'pending'
        returning *
        """,
        (
            bytes_actual,
            completed_at,
            content_type_actual,
            checksum_actual,
            etag_actual,
            upload_id,
        ),
    ).fetchone()
    return None if row is None else Upload.from_row(row)


def claim_for_song(
    conn: psycopg.Connection,
    *,
    upload_id: UUID,
    song_id: UUID,
) -> Upload | None:
    """Attach a completed upload to the song it becomes the source of.

    The partial unique index ``uploads_claim_key`` is what enforces "one claimed
    upload per song"; ``None`` means the claim was refused or the upload is not in
    a claimable state.
    """
    row = conn.execute(
        """
        update public.uploads
        set song_id = %s
        where id = %s and song_id is null and status = 'completed'
        returning *
        """,
        (song_id, upload_id),
    ).fetchone()
    return None if row is None else Upload.from_row(row)


def list_pending_expired(
    conn: psycopg.Connection,
    *,
    limit: int = 100,
) -> list[Upload]:
    """Pending uploads past their deadline, oldest deadline first.

    Supported by ``uploads_pending_expires_at_idx``.
    """
    rows = conn.execute(
        """
        select *
        from public.uploads
        where status = 'pending' and expires_at < now()
        order by expires_at
        limit %s
        """,
        (limit,),
    ).fetchall()
    return [Upload.from_row(row) for row in rows]
