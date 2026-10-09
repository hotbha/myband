"""Shared fixtures for the test suite.

The database tests are integration tests: they need a real PostgreSQL with
``supabase/migrations`` applied, which is what ``supabase start`` gives you. They
skip themselves unless ``MYBAND_TEST_DATABASE_URL`` points at one::

    $env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    pnpm test:api

Nothing here commits: the ``conn`` fixture rolls its transaction back when a test
ends, so the database is left exactly as the seed wrote it. The one test that has
to commit (two competing dispatchers) cleans up after itself.
"""

import json
import os
from collections.abc import Callable, Iterator
from uuid import UUID

import psycopg
import pytest
from app.core.config import get_settings
from app.core.db import connect
from app.core.ids import new_id

TEST_DATABASE_URL = os.environ.get("MYBAND_TEST_DATABASE_URL", "")

# The instance id the local stack's GoTrue stamps on every user it creates.
AUTH_INSTANCE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    """A connection whose transaction is always rolled back."""
    with connect(url=TEST_DATABASE_URL) as connection:
        yield connection
        # Rolled back before the connection's context manager commits, which then
        # has nothing left to commit.
        connection.rollback()


@pytest.fixture
def act_as() -> Callable[[psycopg.Connection, UUID], None]:
    """Become ``authenticated`` with ``auth.uid()`` set, for this transaction.

    This is what the Data API turns a browser request into, minus the HTTP. ``set
    local`` keeps it transaction-scoped, which is why every test rolls back:
    neither the role nor the claim can leak into the next test.
    """

    def _act_as(conn: psycopg.Connection, user_id: UUID) -> None:
        conn.execute("set local role authenticated")
        conn.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": str(user_id), "role": "authenticated"}),),
        )

    return _act_as


@pytest.fixture
def make_user(conn: psycopg.Connection) -> Callable[..., UUID]:
    """Create an ``auth.users`` row; the trigger creates its profile.

    No password is stored: these tests never sign in, they only need rows to own
    things. ``display_name`` lands in ``raw_user_meta_data`` the way a provider
    would send it.
    """

    def _make(*, display_name: str | None = "Test Producer") -> UUID:
        identifier = new_id()
        metadata = {"full_name": display_name} if display_name else {}
        conn.execute(
            """
            insert into auth.users (
                instance_id, id, aud, role, email, email_confirmed_at,
                raw_app_meta_data, raw_user_meta_data, created_at, updated_at
            )
            values (%s, %s, 'authenticated', 'authenticated', %s, now(),
                    '{"provider": "email"}'::jsonb, %s, now(), now())
            """,
            (
                AUTH_INSTANCE_ID,
                identifier,
                f"user-{identifier}@myband.test",
                json.dumps(metadata),
            ),
        )
        return identifier

    return _make


@pytest.fixture
def user_id(make_user: Callable[..., UUID]) -> UUID:
    """One account."""
    return make_user()


@pytest.fixture
def make_object_key(user_id: UUID) -> Callable[..., str]:
    """Build keys that satisfy the ``users/<uuid>/...`` CHECK constraints."""

    def _make(*, prefix: str = "uploads", name: str = "test.wav") -> str:
        return f"users/{user_id}/{prefix}/{new_id()}/{name}"

    return _make


@pytest.fixture
def song_id(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
) -> UUID:
    """One song owned by ``user_id``."""
    row = conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, 'Test Song', %s)
        returning id
        """,
        (new_id(), user_id, make_object_key(name="test-song.wav")),
    ).fetchone()
    return row["id"]


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make ``get_settings()`` read this run's environment, not a developer's.

    Settings are cached per process and ``DATABASE_URL`` is required, so the cache
    is cleared either side of the test and pointed at the test database. Services
    read configuration even when they never open a connection themselves - the
    pipeline version a job is stamped with, the presign TTL - and those values have
    to come from the same place the tests do.
    """
    if TEST_DATABASE_URL:
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
