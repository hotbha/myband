"""Data access for ``public.songs``.

One row per uploaded recording. Nothing here edits ``source_object_key``: the key
is immutable, and a re-upload becomes a new song.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    # The analysis headline, denormalised so the library list needs no join
    # (migration 04). Written by the worker, null until something has analysed.
    bpm: Decimal | None
    musical_key: str | None
    source_object_key: str
    source_checksum: str | None
    source_bytes: int | None
    source_content_type: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class LibraryStats:
    """How much the platform holds, as opposed to what it is doing."""

    songs: int
    song_owners: int


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


def library_stats(conn: psycopg.Connection) -> LibraryStats:
    """How many songs the platform holds, and how many accounts own at least one.

    Deliberately about the library rather than about accounts: this API knows songs,
    and ``count(distinct user_id)`` answers "how many people have uploaded something"
    without reading the auth schema that owns users.
    """
    row = conn.execute(
        """
        select
            count(*) as songs,
            count(distinct user_id) as song_owners
        from public.songs
        where deleted_at is null
        """
    ).fetchone()
    return LibraryStats(songs=row["songs"], song_owners=row["song_owners"])


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


def set_analysis(
    conn: psycopg.Connection,
    *,
    song_id: UUID,
    duration_ms: int,
    bpm: Decimal | float,
    musical_key: str,
) -> bool:
    """Record what the analysis measured: length, tempo and key.

    Called by the analysis worker inside the same transaction as ``queue.complete``,
    which is what makes the pointer and the headline move together - a library row can
    never claim a finished analysis without the numbers that came with it.

    ``duration_ms`` is written here rather than at upload time because until something
    has decoded the file, the only length anyone has is the container's guess. The
    worker measures it from the header, and this is one of the three columns the
    library list reads.

    Scoped to a song that is not deleted, and returns ``False`` when the row is gone, so
    a worker racing a delete does not resurrect a soft-deleted song's numbers.
    """
    row = conn.execute(
        """
        update public.songs
        set duration_ms = %s, bpm = %s, musical_key = %s
        where id = %s and deleted_at is null
        returning id
        """,
        (
            duration_ms,
            Decimal(str(bpm)).quantize(Decimal("0.01")),
            musical_key,
            song_id,
        ),
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
