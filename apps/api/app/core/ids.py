"""UUIDv7 primary keys.

Every table in ``supabase/migrations`` is keyed by a UUIDv7 that the application
generates - there is no database default (see docs/schema.md, "Why ids come from
the application"). A v7 id is time ordered, so inserts land in the rightmost page
of the primary key index instead of scattering across it the way random v4 ids
do, and the id doubles as a rough creation timestamp.

Python 3.14 ships ``uuid.uuid7()``; this project targets 3.12, so the small
``uuid6`` package provides the same generator.
"""

from uuid import UUID

from uuid6 import uuid7


def new_id() -> UUID:
    """Return a new time-ordered UUIDv7."""
    return uuid7()


def is_uuid7(value: UUID) -> bool:
    """True when ``value`` carries the v7 version nibble."""
    return value.version == 7
