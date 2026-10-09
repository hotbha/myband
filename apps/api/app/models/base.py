"""Shared plumbing for the row dataclasses in this package.

Each table in ``supabase/migrations`` gets one module here: a frozen dataclass
with a field per column and the handful of statements that table needs. Rows come
back from psycopg as plain dicts (``row_factory=dict_row``), and ``Record`` turns
one into the dataclass.
"""

import dataclasses
from collections.abc import Mapping
from typing import Any, Self


class Record:
    """Base class for a table row.

    ``from_row`` fills every declared field from a dict row, so a column dropped
    or renamed by a migration fails loudly on the first query instead of quietly
    turning into a ``None``. Convert sql rows with ``select *`` rather than a
    column list so the two stay in step.
    """

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | None) -> Self:
        if row is None:
            raise LookupError(f"expected a {cls.__name__} row, got None")
        names = [column.name for column in dataclasses.fields(cls)]  # type: ignore[arg-type]
        return cls(**{name: row[name] for name in names})
