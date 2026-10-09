"""Data access for ``public.songs``.

One row per uploaded recording. Nothing here edits ``source_object_key``: the key
is immutable, and a re-upload becomes a new song.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record


@dataclass(frozen=True, slots=True)
class Song(Record):
    id: UUID
    user_id: UUID
    project_id: UUID | None
    latest_job_id: UUID | None
    title: str
    artist: str | None
    duration_ms: int | None
    source_object_key: str
    source_checksum: str | None
    source_bytes: int | None
    source_content_type: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def _clean(value: str | None, *, limit: int) -> str | None:
    """Trim, drop empties and cap the length, so a column CHECK cannot fire."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else None


def insert(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    title: str,
    source_object_key: str,
    song_id: UUID | None = None,
    project_id: UUID | None = None,
    artist: str | None = None,
    duration_ms: int | None = None,
    source_checksum: str | None = None,
    source_bytes: int | None = None,
    source_content_type: str | None = None,
) -> Song:
    """Insert one song, generating its UUIDv7 unless the caller supplied one."""
    row = conn.execute(
        """
        insert into public.songs (
            id, user_id, project_id, title, artist, duration_ms,
            source_object_key, source_checksum, source_bytes, source_content_type
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (
            song_id or new_id(),
            user_id,
            project_id,
            title.strip()[:200],
            _clean(artist, limit=200),
            duration_ms,
            source_object_key,
            source_checksum,
            source_bytes,
            source_content_type,
        ),
    ).fetchone()
    return Song.from_row(row)


def get(conn: psycopg.Connection, song_id: UUID) -> Song | None:
    """Fetch one song, deleted or not."""
    row = conn.execute(
        "select * from public.songs where id = %s",
        (song_id,),
    ).fetchone()
    return None if row is None else Song.from_row(row)


def list_for_user(
    conn: psycopg.Connection,
    user_id: UUID,
    *,
    limit: int = 50,
) -> list[Song]:
    """The user's library, newest first. Deleted songs are left out."""
    rows = conn.execute(
        """
        select *
        from public.songs
        where user_id = %s and deleted_at is null
        order by created_at desc
        limit %s
        """,
        (user_id, limit),
    ).fetchall()
    return [Song.from_row(row) for row in rows]


def set_latest_job(
    conn: psycopg.Connection,
    *,
    song_id: UUID,
    job_id: UUID | None,
) -> bool:
    """Point a song at its newest analysis job.

    Called by the queue service when a job finishes, inside the same transaction
    as the job update, so the library never shows a job that does not exist yet.
    """
    row = conn.execute(
        "update public.songs set latest_job_id = %s where id = %s returning id",
        (job_id, song_id),
    ).fetchone()
    return row is not None


def soft_delete(conn: psycopg.Connection, *, song_id: UUID) -> bool:
    """Mark a song deleted, report whether this call is what did it.

    The audio object stays in R2: a soft delete is reversible, and the object is
    only owed a delete once the row itself is gone.
    """
    row = conn.execute(
        """
        update public.songs
        set deleted_at = now()
        where id = %s and deleted_at is null
        returning id
        """,
        (song_id,),
    ).fetchone()
    return row is not None
