"""Data access for ``public.projects``.

A project groups songs. Deleting one is a soft delete: the songs keep their
``project_id`` and disappear together with the project when the UI filters on
``deleted_at``, which is why nothing here unfiles anything.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record


@dataclass(frozen=True, slots=True)
class Project(Record):
    id: UUID
    owner_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def insert(
    conn: psycopg.Connection,
    *,
    owner_id: UUID,
    name: str,
    project_id: UUID | None = None,
) -> Project:
    """Create a project. ``name`` is trimmed and capped to fit the CHECK."""
    row = conn.execute(
        """
        insert into public.projects (id, owner_id, name)
        values (%s, %s, %s)
        returning *
        """,
        (project_id or new_id(), owner_id, name.strip()[:120]),
    ).fetchone()
    return Project.from_row(row)


def get(conn: psycopg.Connection, project_id: UUID) -> Project | None:
    """Fetch one project, deleted or not."""
    row = conn.execute(
        "select * from public.projects where id = %s",
        (project_id,),
    ).fetchone()
    return None if row is None else Project.from_row(row)


def list_for_owner(
    conn: psycopg.Connection,
    owner_id: UUID,
    *,
    limit: int = 50,
) -> list[Project]:
    """An owner's projects, newest first, deleted ones excluded."""
    rows = conn.execute(
        """
        select *
        from public.projects
        where owner_id = %s and deleted_at is null
        order by created_at desc
        limit %s
        """,
        (owner_id, limit),
    ).fetchall()
    return [Project.from_row(row) for row in rows]


def rename(conn: psycopg.Connection, *, project_id: UUID, name: str) -> Project | None:
    """Rename a live project, or return ``None`` when it is gone."""
    row = conn.execute(
        """
        update public.projects
        set name = %s
        where id = %s and deleted_at is null
        returning *
        """,
        (name.strip()[:120], project_id),
    ).fetchone()
    return None if row is None else Project.from_row(row)


def soft_delete(conn: psycopg.Connection, *, project_id: UUID) -> bool:
    """Mark a project deleted, report whether this call is what did it."""
    row = conn.execute(
        """
        update public.projects
        set deleted_at = now()
        where id = %s and deleted_at is null
        returning id
        """,
        (project_id,),
    ).fetchone()
    return row is not None
