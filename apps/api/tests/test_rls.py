"""Row level security and cascades, exercised the way the browser would.

Every statement here runs as the ``authenticated`` role with a JWT claim set,
which is the only way to find out whether a policy actually holds. The structure
those policies depend on - tables, grants, indexes - is asserted in
``tests/test_schema.py``; the matrix they implement is in ``docs/schema.md``.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable
from uuid import UUID

import psycopg
import pytest
from app.core.ids import new_id

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

ActAs = Callable[[psycopg.Connection, UUID], None]


def test_owner_sees_only_their_own_rows(
    conn: psycopg.Connection,
    act_as: ActAs,
    make_user: Callable[..., UUID],
    user_id: UUID,
    song_id: UUID,
) -> None:
    """The other account's song exists, and is invisible."""
    stranger = make_user()
    conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, 'Someone Else', %s)
        """,
        (new_id(), stranger, f"users/{stranger}/uploads/{new_id()}/theirs.wav"),
    )

    act_as(conn, user_id)
    visible = conn.execute("select id from public.songs").fetchall()

    assert [row["id"] for row in visible] == [song_id]


def test_soft_deleted_rows_are_invisible(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    conn.execute("update public.songs set deleted_at = now() where id = %s", (song_id,))

    act_as(conn, user_id)

    assert conn.execute("select count(*) as n from public.songs").fetchone()["n"] == 0


def test_authenticated_cannot_insert_a_job(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """The API is the writer; a browser session has no INSERT grant at all."""
    act_as(conn, user_id)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute(
            """
            insert into public.analysis_jobs (
                id, user_id, song_id, pipeline_version, source_object_key
            )
            values (%s, %s, %s, '0.1.0', %s)
            """,
            (new_id(), user_id, song_id, f"users/{user_id}/uploads/{new_id()}/x.wav"),
        )


def test_column_grant_blocks_writes_outside_the_grant(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """songs has UPDATE on its four user-owned columns, and only on those."""
    act_as(conn, user_id)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("update public.songs set duration_ms = 1000 where id = %s", (song_id,))


def test_a_song_cannot_be_filed_into_someone_elses_project(
    conn: psycopg.Connection,
    act_as: ActAs,
    make_user: Callable[..., UUID],
    user_id: UUID,
    song_id: UUID,
) -> None:
    """The WITH CHECK on songs_update_own is what stops it."""
    stranger = make_user()
    project = conn.execute(
        """
        insert into public.projects (id, owner_id, name)
        values (%s, %s, 'Theirs')
        returning id
        """,
        (new_id(), stranger),
    ).fetchone()

    act_as(conn, user_id)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute(
            "update public.songs set project_id = %s where id = %s",
            (project["id"], song_id),
        )


def test_a_song_can_be_filed_into_the_callers_own_project(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """The other half of the WITH CHECK: the exists branch really can pass."""
    project = conn.execute(
        """
        insert into public.projects (id, owner_id, name)
        values (%s, %s, 'Mine')
        returning id
        """,
        (new_id(), user_id),
    ).fetchone()

    act_as(conn, user_id)

    changed = conn.execute(
        "update public.songs set project_id = %s where id = %s",
        (project["id"], song_id),
    )

    assert changed.rowcount == 1


def test_own_song_can_be_renamed(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    act_as(conn, user_id)

    changed = conn.execute(
        "update public.songs set title = 'Renamed' where id = %s",
        (song_id,),
    )

    assert changed.rowcount == 1


def test_deleting_is_not_a_column_the_browser_may_write(
    conn: psycopg.Connection,
    act_as: ActAs,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """`deleted_at` is absent from both UPDATE grants - deleting is an API job.

    It has to enqueue the song's R2 objects for removal and settle any job running
    on it, in one transaction. A one-column UPDATE from a browser session would
    skip that, and it is also the one write that cannot pass the songs WITH CHECK
    once the row stops being visible to the SELECT policy (docs/schema.md).
    """
    act_as(conn, user_id)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute(
            "update public.songs set deleted_at = now() where id = %s",
            (song_id,),
        )


def _add_job_with_result(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    source_key: str,
) -> UUID:
    """A succeeded job, one result and the song pointer, as the queue writes them."""
    job_id = new_id()
    conn.execute(
        """
        insert into public.analysis_jobs (
            id, user_id, song_id, status, pipeline_version, source_object_key, finished_at
        )
        values (%s, %s, %s, 'succeeded', '0.1.0', %s, now())
        """,
        (job_id, user_id, song_id, source_key),
    )
    conn.execute(
        """
        insert into public.analysis_results (id, job_id, user_id, kind, summary)
        select %s, j.id, j.user_id, 'bpm', '{"bpm": 120}'::jsonb
        from public.analysis_jobs j
        where j.id = %s
        """,
        (new_id(), job_id),
    )
    conn.execute(
        "update public.songs set latest_job_id = %s where id = %s",
        (job_id, song_id),
    )
    return job_id


def _count_rows(conn: psycopg.Connection, table: str, column: str, value: UUID) -> int:
    row = conn.execute(
        f"select count(*) as n from public.{table} where {column} = %s",
        (value,),
    ).fetchone()
    return row["n"]


def test_deleting_a_song_removes_its_jobs_and_results(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """Also proves the songs <-> analysis_jobs cycle resolves on delete."""
    job_id = _add_job_with_result(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    conn.execute("delete from public.songs where id = %s", (song_id,))

    assert _count_rows(conn, "analysis_jobs", "song_id", song_id) == 0
    assert _count_rows(conn, "analysis_results", "job_id", job_id) == 0


def test_deleting_a_user_removes_their_data(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    _add_job_with_result(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )
    conn.execute(
        """
        insert into public.uploads (
            id, user_id, song_id, object_key, status, bytes_actual, completed_at, expires_at
        )
        values (%s, %s, %s, %s, 'completed', 10, now(), now() + interval '1 day')
        """,
        (new_id(), user_id, song_id, make_object_key(name="claimed.wav")),
    )
    gc_id = new_id()
    conn.execute(
        """
        insert into public.storage_gc_queue (id, user_id, object_key, reason)
        values (%s, %s, %s, 'manual')
        """,
        (gc_id, user_id, make_object_key(name="orphan.wav")),
    )

    conn.execute("delete from auth.users where id = %s", (user_id,))

    assert _count_rows(conn, "profiles", "id", user_id) == 0
    assert _count_rows(conn, "songs", "user_id", user_id) == 0
    assert _count_rows(conn, "uploads", "user_id", user_id) == 0
    assert _count_rows(conn, "analysis_jobs", "user_id", user_id) == 0
    assert _count_rows(conn, "analysis_results", "user_id", user_id) == 0

    # The GC row survives on purpose: removing those objects is exactly what
    # closing an account owes the bucket, so the work outlives its owner.
    row = conn.execute(
        "select user_id, completed_at from public.storage_gc_queue where id = %s",
        (gc_id,),
    ).fetchone()
    assert row is not None
    assert row["user_id"] is None
    assert row["completed_at"] is None
