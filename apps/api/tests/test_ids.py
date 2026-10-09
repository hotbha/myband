"""UUIDv7 generation - the one part of the data layer that needs no database.

The ids matter to the schema: every primary key in ``supabase/migrations`` is one
of these, and there is no database default to fall back on.
"""

import time
from uuid import uuid4

from app.core.ids import is_uuid7, new_id


def test_new_id_is_uuid7() -> None:
    identifier = new_id()
    assert identifier.version == 7
    assert is_uuid7(identifier)


def test_new_id_is_time_ordered() -> None:
    """Ordering holds across milliseconds, which is what index locality needs.

    Inside a single millisecond the remaining bits are random by design - RFC 9562
    does not require a monotonic counter - so this waits out the clock's
    resolution instead of asserting something the generator never promised.
    """
    first = new_id()
    time.sleep(0.01)
    second = new_id()
    assert first < second


def test_is_uuid7_rejects_other_versions() -> None:
    assert not is_uuid7(uuid4())
