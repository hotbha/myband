"""What the stale-job sweep does, and what it deliberately leaves alone.

The sweep exists because a process that was killed cannot report that it died. That
is the whole reason its candidate set is ``dispatched`` and ``running`` rather than
"everything in flight": a ``queued`` job is waiting for a dispatcher, not for a
worker, so its age says nothing about whether anything went wrong. Failing it would
throw away work nobody ever started.

Every case runs inside the rolled-back transaction the ``conn`` fixture provides. The
ones that assert about the *set* of jobs the sweep picks take ``own_queue`` first, so
the answer is about the jobs this test made rather than about whatever else the
database happens to be holding.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from app.core.ids import new_id
from app.models import analysis_job
from app.models.analysis_job import AnalysisJob
from app.services import queue
from tests.support import claim_own_job

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

PIPELINE_VERSION = "0.1.0"

# A window wide enough that no row can be alive: the sweep looks for a last sign of
# life older than ``now - older_than``, so a negative duration puts the horizon in
# the future. Whatever it spares, it spares because of the status it is in.
NOTHING_IS_ALIVE = timedelta(days=-1)

ALL_STATUSES = ("queued", "dispatched", "running", "succeeded", "failed", "canceled")


def _song(conn: psycopg.Connection, *, user_id: UUID, make_object_key: Callable[..., str]) -> UUID:
    """A song of its own, because a song can only hold one job at a time."""
    row = conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, 'Sweep Test Song', %s)
        returning id
        """,
        (new_id(), user_id, make_object_key(name="sweep.wav")),
    ).fetchone()
    return row["id"]


def _job_in_status(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    make_object_key: Callable[..., str],
    status: str,
) -> AnalysisJob:
    """A job sitting in ``status``, reached the way the queue reaches it.

    ``canceled`` is written directly: nothing in the service cancels a job yet - the
    product has no cancel button, and ``queue`` deliberately has no ``cancel`` - so
    the row is the schema's terminal-but-canceled state rather than a path a caller
    can walk. It is here because the sweep's contract is about the whole status
    column, not only about the statuses the product can produce today.
    """
    song_id = _song(conn, user_id=user_id, make_object_key=make_object_key)
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=make_object_key(name="sweep.wav"),
    )
    assert outcome.job is not None
    if status == "queued":
        return outcome.job

    dispatched = queue.mark_dispatched(
        conn,
        job=claim_own_job(conn, song_id=song_id),
        runpod_job_id="rp_sweep",
    )
    assert dispatched is not None
    if status == "dispatched":
        return dispatched

    running = queue.mark_running(conn, job=dispatched)
    assert running is not None
    if status == "running":
        return running

    if status == "succeeded":
        assert queue.complete(conn, job=running, results=[]) is not None
    elif status == "failed":
        assert queue.fail(conn, job=running, error_code="decode_error") is not None
    else:
        conn.execute(
            """
            update public.analysis_jobs
            set status = 'canceled', finished_at = now()
            where id = %s
            """,
            (running.id,),
        )

    settled = analysis_job.get(conn, running.id)
    assert settled is not None
    assert settled.status == status
    return settled


def test_a_queued_job_is_never_reaped(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Waiting for a dispatcher is not a failure, so the job is left alone.

    The window is so wide that nothing in the table can be alive, which is the point:
    age is not evidence of anything, and the only thing left that can spare this job
    is the status it is in.
    """
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=make_object_key(name="source.wav"),
    )
    assert outcome.job is not None

    reaped = {job.id for job in queue.reap_stale(conn, older_than=NOTHING_IS_ALIVE)}

    assert outcome.job.id not in reaped
    still_queued = analysis_job.get(conn, outcome.job.id)
    assert still_queued is not None
    assert still_queued.status == "queued"


def test_only_a_job_a_worker_holds_can_go_stale(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Six jobs, one per status; only the two a worker was handed are candidates.

    Every row is stale on age, so the status is the only variable left. A job nobody
    was ever handed and a job that already finished are both out of reach - and the
    sweep has to agree with the query it is built on, not only the query on its own.
    """
    jobs = {
        status: _job_in_status(
            conn, user_id=user_id, make_object_key=make_object_key, status=status
        )
        for status in ALL_STATUSES
    }

    candidates = analysis_job.list_stale_active(
        conn,
        before=datetime.now(UTC) + timedelta(days=365),
        limit=queue.MAX_BATCH,
    )

    assert {candidate.id for candidate in candidates} == {
        jobs["dispatched"].id,
        jobs["running"].id,
    }

    reaped = {job.id for job in queue.reap_stale(conn, older_than=NOTHING_IS_ALIVE)}

    assert reaped == {jobs["dispatched"].id, jobs["running"].id}


def test_a_sweep_is_bounded_by_its_limit(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A sweep takes what it was told to take, so a backlog cannot stall the worker.

    Which two of the three come back is deliberately not asserted: all three rows
    share this transaction's ``now()``, so "oldest first" has nothing to order them
    by here.
    """
    jobs = [
        _job_in_status(conn, user_id=user_id, make_object_key=make_object_key, status="dispatched")
        for _ in range(3)
    ]

    reaped = queue.reap_stale(conn, older_than=NOTHING_IS_ALIVE, limit=2)

    assert len(reaped) == 2
    survivors = [job for job in jobs if _status_of(conn, job) == "dispatched"]
    assert len(survivors) == 1


def _status_of(conn: psycopg.Connection, job: AnalysisJob) -> str:
    """Read a job's status back, which is the only thing that survives a sweep."""
    refreshed = analysis_job.get(conn, job.id)
    assert refreshed is not None
    return refreshed.status
