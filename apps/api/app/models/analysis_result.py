"""Data access for ``public.analysis_results``.

One row per artifact kind per job. Small payloads live inline in ``summary``,
larger ones in R2 behind ``object_key``; ``ResultInput`` is what a worker hands
over and is the only way this module will write a row.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from app.core.ids import new_id
from app.models.base import Record
from psycopg.types.json import Jsonb

# Kept in step with the CHECK constraints on `kind` and `payload_bytes`.
KINDS = frozenset({"bpm", "key", "chords", "midi", "sections"})
MAX_SUMMARY_BYTES = 8192


@dataclass(frozen=True, slots=True)
class AnalysisResult(Record):
    id: UUID
    job_id: UUID
    user_id: UUID
    kind: str
    summary: dict[str, Any]
    payload_bytes: int
    object_key: str | None
    object_bytes: int | None
    object_content_type: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ResultInput:
    """One artifact a worker produced, validated before it reaches the database.

    ``payload_bytes`` is measured here instead of trusted from the caller, and
    checked against the same cap the column constraint enforces, so an oversized
    inline payload fails with a message naming the kind rather than at the CHECK.
    """

    kind: str
    summary: dict[str, Any] = field(default_factory=dict)
    object_key: str | None = None
    object_bytes: int | None = None
    object_content_type: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown artifact kind: {self.kind!r}")
        if (self.object_key is None) != (self.object_bytes is None):
            raise ValueError("object_key and object_bytes are set together, or not at all")
        if self.payload_bytes > MAX_SUMMARY_BYTES:
            raise ValueError(
                f"{self.kind} summary is {self.payload_bytes} bytes and the limit "
                f"is {MAX_SUMMARY_BYTES}: keep only a digest inline and put the "
                "full payload in R2"
            )

    @property
    def payload_bytes(self) -> int:
        """UTF-8 length of the compact JSON encoding of ``summary``."""
        encoded = json.dumps(self.summary, separators=(",", ":"), ensure_ascii=False)
        return len(encoded.encode("utf-8"))


def upsert_many(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    results: Sequence[ResultInput],
) -> int:
    """Write a job's artifacts, returning how many rows were written.

    ``user_id`` is copied from the job by the statement itself - a result can
    never be attributed to another account, and the composite foreign key would
    reject it if it tried. Idempotent on (job_id, kind), so re-running a pipeline
    overwrites its earlier output instead of duplicating it.

    A job that does not exist selects no rows and writes nothing; the caller is
    expected to hold the job (the queue service always does).
    """
    if not results:
        return 0
    parameters = [
        (
            new_id(),
            result.kind,
            Jsonb(result.summary),
            result.payload_bytes,
            result.object_key,
            result.object_bytes,
            result.object_content_type,
            job_id,
        )
        for result in results
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            insert into public.analysis_results (
                id, job_id, user_id, kind, summary, payload_bytes,
                object_key, object_bytes, object_content_type
            )
            select %s, j.id, j.user_id, %s, %s, %s, %s, %s, %s
            from public.analysis_jobs j
            where j.id = %s
            on conflict (job_id, kind) do update set
                summary = excluded.summary,
                payload_bytes = excluded.payload_bytes,
                object_key = excluded.object_key,
                object_bytes = excluded.object_bytes,
                object_content_type = excluded.object_content_type
            """,
            parameters,
        )
    return len(parameters)


def list_for_job(conn: psycopg.Connection, job_id: UUID) -> list[AnalysisResult]:
    """Every artifact of one job, in a stable order."""
    rows = conn.execute(
        """
        select *
        from public.analysis_results
        where job_id = %s
        order by kind
        """,
        (job_id,),
    ).fetchall()
    return [AnalysisResult.from_row(row) for row in rows]
