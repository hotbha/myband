"""Data access for ``public.profiles``.

One row per account, created by the ``on_auth_user_created`` trigger - there is no
insert here, and only the two display fields are writable by their owner, which
the column-level GRANT in migration 03 mirrors.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from app.models.base import Record


@dataclass(frozen=True, slots=True)
class Profile(Record):
    id: UUID
    email: str | None
    display_name: str | None
    avatar_url: str | None
    plan: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def get(conn: psycopg.Connection, profile_id: UUID) -> Profile | None:
    """Fetch a profile by its auth.users id, which is also the profile id."""
    row = conn.execute(
        "select * from public.profiles where id = %s",
        (profile_id,),
    ).fetchone()
    return None if row is None else Profile.from_row(row)


def update_display_fields(
    conn: psycopg.Connection,
    *,
    profile_id: UUID,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> Profile | None:
    """Set display_name and/or avatar_url on a live profile.

    A field that is not passed is left alone; clearing one is the web form's job
    to express, and ``normalize_profile`` trims, truncates and drops non-https
    avatars before the row is stored.
    """
    row = conn.execute(
        """
        update public.profiles
        set display_name = coalesce(%s, display_name),
            avatar_url = coalesce(%s, avatar_url)
        where id = %s and deleted_at is null
        returning *
        """,
        (display_name, avatar_url, profile_id),
    ).fetchone()
    return None if row is None else Profile.from_row(row)
