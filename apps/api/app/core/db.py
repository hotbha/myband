"""PostgreSQL access.

psycopg 3, no ORM: the schema is owned by ``supabase/migrations`` and the SQL
lives in ``app/models``. One connection at a time; pooling arrives with the first
route (`pnpm dev:api` serves one process, and Supavisor already pools in front of
the database).

Supavisor, Supabase's pooler, runs in transaction mode by default and hands each
statement to whichever backend is free. A prepared statement is therefore not
safe across statements on a pooled connection - pass ``prepare_threshold=None``
when connecting through it::

    with connect(url=pooler_url, prepare_threshold=None) as conn: ...

Direct connections (local development, migrations, queue workers) keep the
default. Nothing in this module sets the pooler flag yet, because nothing in this
phase runs behind it.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from app.core.config import get_settings
from psycopg.rows import dict_row

# psycopg prepares a statement automatically after it has been seen this many
# times. None disables preparation entirely (what the transaction pooler needs).
DEFAULT_PREPARE_THRESHOLD = 5


@contextmanager
def connect(
    *,
    url: str | None = None,
    prepare_threshold: int | None = DEFAULT_PREPARE_THRESHOLD,
) -> Iterator[psycopg.Connection]:
    """Yield a connection that returns dict rows and is closed on exit.

    The connection's own context manager commits when the block ends normally and
    rolls back when it raises, so::

        with connect() as conn:
            ...

    is exactly one transaction. Functions in this codebase never commit
    themselves - the caller owns the transaction boundary.
    """
    connection_string = url or get_settings().database_url
    with psycopg.connect(
        connection_string,
        row_factory=dict_row,
        prepare_threshold=prepare_threshold,
    ) as conn:
        yield conn
