"""Schema contract tests: tables, policies, grants, triggers and indexes.

Every assertion here maps to a sentence in ``docs/schema.md``. This is the file
that fails when a later migration undoes a decision by accident. What the
policies actually *do* - who can see and change what, and what a delete cascades
into - is asserted in ``tests/test_rls.py``.

Needs a migrated database - ``supabase start``, then::

    $env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    pnpm test:api
"""

import os
from collections.abc import Callable
from uuid import UUID

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

TABLES = (
    "profiles",
    "projects",
    "songs",
    "uploads",
    "analysis_jobs",
    "analysis_results",
    "storage_gc_queue",
)

# Everything except the internal queue, which a browser session cannot read.
READABLE_BY_AUTHENTICATED = TABLES[:-1]


def _has_privilege(
    conn: psycopg.Connection,
    role: str,
    table: str,
    privilege: str,
) -> bool:
    row = conn.execute(
        "select has_table_privilege(%s::name, %s::text, %s::text) as allowed",
        (role, f"public.{table}", privilege),
    ).fetchone()
    return bool(row["allowed"])


def test_all_seven_tables_exist_with_rls_enabled(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        """
        select c.relname, c.relrowsecurity
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
        """
    ).fetchall()

    assert {row["relname"] for row in rows} == set(TABLES)
    assert [row["relname"] for row in rows if not row["relrowsecurity"]] == []


def test_policies_are_ownership_only(conn: psycopg.Connection) -> None:
    """SELECT everywhere, UPDATE on the three user-editable tables.

    Nothing grants DELETE (deletion is a soft delete) and nothing grants INSERT
    (the API is the only writer), which is what the rest of this file assumes.
    """
    rows = conn.execute(
        "select tablename, cmd from pg_policies where schemaname = 'public'"
    ).fetchall()

    assert {(row["tablename"], row["cmd"]) for row in rows} == {
        ("profiles", "SELECT"),
        ("profiles", "UPDATE"),
        ("projects", "SELECT"),
        ("projects", "UPDATE"),
        ("songs", "SELECT"),
        ("songs", "UPDATE"),
        ("uploads", "SELECT"),
        ("analysis_jobs", "SELECT"),
        ("analysis_results", "SELECT"),
    }


def test_anon_can_touch_nothing(conn: psycopg.Connection) -> None:
    for table in TABLES:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert not _has_privilege(conn, "anon", table, privilege), (table, privilege)


def test_authenticated_may_read_but_not_write(conn: psycopg.Connection) -> None:
    for table in TABLES:
        expected = table in READABLE_BY_AUTHENTICATED
        assert _has_privilege(conn, "authenticated", table, "SELECT") is expected, table
        assert not _has_privilege(conn, "authenticated", table, "INSERT"), table
        assert not _has_privilege(conn, "authenticated", table, "DELETE"), table
        assert not _has_privilege(conn, "authenticated", table, "TRUNCATE"), table


def test_expected_indexes_exist(conn: psycopg.Connection) -> None:
    """The indexing plan as a set: adding or dropping one is a design change."""
    rows = conn.execute("select indexname from pg_indexes where schemaname = 'public'").fetchall()

    assert {row["indexname"] for row in rows} == {
        "profiles_pkey",
        "projects_pkey",
        "projects_owner_id_created_at_idx",
        "songs_pkey",
        "songs_user_id_created_at_idx",
        "songs_project_id_idx",
        "songs_latest_job_id_idx",
        "uploads_pkey",
        "uploads_object_key_key",
        "uploads_claim_key",
        "uploads_user_id_created_at_idx",
        "uploads_pending_expires_at_idx",
        "analysis_jobs_pkey",
        "analysis_jobs_id_user_id_key",
        "analysis_jobs_song_id_created_at_idx",
        "analysis_jobs_user_id_created_at_idx",
        "analysis_jobs_runpod_job_id_idx",
        "analysis_jobs_active_created_at_idx",
        "analysis_jobs_one_active_per_song_key",
        "analysis_jobs_usage_idx",
        "analysis_results_pkey",
        "analysis_results_job_kind_key",
        "analysis_results_user_id_idx",
        "storage_gc_queue_pkey",
        "storage_gc_queue_object_key_key",
        "storage_gc_queue_due_idx",
        "storage_gc_queue_user_id_idx",
    }


def test_partial_indexes_are_partial_where_it_counts(conn: psycopg.Connection) -> None:
    """The three partial indexes exist for a reason, and it shows in the DDL."""
    definitions = {
        row["indexname"]: row["indexdef"]
        for row in conn.execute(
            "select indexname, indexdef from pg_indexes where schemaname = 'public'"
        ).fetchall()
    }

    # The queue seam: only work that is still in flight deserves an entry.
    seam = definitions["analysis_jobs_active_created_at_idx"]
    assert "dispatched" in seam and "WHERE" in seam.upper()
    # The usage meter: failed and canceled jobs are never billable.
    meter = definitions["analysis_jobs_usage_idx"]
    assert "succeeded" in meter and "WHERE" in meter.upper()
    # One active attempt per song.
    one_active = definitions["analysis_jobs_one_active_per_song_key"]
    assert "UNIQUE" in one_active.upper()


def test_updated_at_triggers_are_attached(conn: psycopg.Connection) -> None:
    """Six tables carry updated_at; storage_gc_queue stamps each change itself."""
    rows = conn.execute(
        """
        select c.relname, t.tgname
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and not t.tgisinternal
        """
    ).fetchall()
    triggers = {(row["relname"], row["tgname"]) for row in rows}

    for table in TABLES:
        expected = table != "storage_gc_queue"
        assert ((table, "set_updated_at") in triggers) is expected, table
    assert ("profiles", "normalize_profile") in triggers


def test_signup_creates_a_profile(conn: psycopg.Connection, user_id: UUID) -> None:
    row = conn.execute(
        "select email, display_name from public.profiles where id = %s",
        (user_id,),
    ).fetchone()

    assert row is not None
    assert row["display_name"] == "Test Producer"


def test_a_long_provider_name_cannot_abort_a_signup(
    conn: psycopg.Connection,
    make_user: Callable[..., UUID],
) -> None:
    """normalize_profile truncates, so a 200 character name still signs up."""
    identifier = make_user(display_name="N" * 200)

    row = conn.execute(
        "select display_name from public.profiles where id = %s",
        (identifier,),
    ).fetchone()

    assert row["display_name"] == "N" * 60


def test_normalize_profile_trims_and_rejects_non_https(
    conn: psycopg.Connection,
    user_id: UUID,
) -> None:
    conn.execute(
        """
        update public.profiles
        set display_name = '  Padded Name  ',
            avatar_url = 'http://insecure.example/avatar.png'
        where id = %s
        """,
        (user_id,),
    )

    row = conn.execute(
        "select display_name, avatar_url from public.profiles where id = %s",
        (user_id,),
    ).fetchone()

    assert row["display_name"] == "Padded Name"
    assert row["avatar_url"] is None
