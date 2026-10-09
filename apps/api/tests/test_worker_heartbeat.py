"""The thread that keeps a running job's lease alive.

The one worker suite that commits on purpose. A heartbeat exists to be visible to *other*
connections - that is the whole reason it is not written on the job's own connection - so
a test that kept everything inside one rolled-back transaction could not observe it at
all. The job is committed, the thread writes on its own connections, and the test removes
what it made when it is done (the way the SKIP LOCKED case in ``test_queue.py`` does).

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

import psycopg
import pytest
from app.core.ids import new_id
from app.models import analysis_job
from app.models.analysis_job import AnalysisJob
from app.services import queue
from app.workers.heartbeat import Heartbeat

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

# How long a test waits for another thread's write to land before calling it a failure.
WAIT_SECONDS = 5.0

# Faster than any real worker beats, so a test is over in a fraction of a second. The
# class floors the interval, so this is the smallest one it will accept.
INTERVAL_SECONDS = 0.05


@pytest.fixture
def committed_job(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> Iterator[AnalysisJob]:
    """A running job, committed, and cleaned up however the test ends.

    Committed because the heartbeat's own connections have to see it - and deleted
    afterwards because the ``conn`` fixture's rollback no longer covers it.
    """
    job = _start(conn, user_id=user_id, song_id=song_id, source_key=make_object_key(name="s.wav"))
    conn.commit()

    yield job

    conn.rollback()
    conn.execute("delete from public.songs where id = %s", (song_id,))
    conn.execute("delete from auth.users where id = %s", (user_id,))
    conn.commit()


def test_a_running_job_is_kept_alive(
    conn: psycopg.Connection,
    committed_job: AnalysisJob,
    settings_env: None,
) -> None:
    """What the thread is for: ``heartbeat_at`` moves while the worker is busy."""
    before = _heartbeat_of(conn, committed_job.id)

    with Heartbeat(
        job_id=committed_job.id,
        interval_seconds=INTERVAL_SECONDS,
    ) as heartbeat:
        assert _wait_until(lambda: _heartbeat_of(conn, committed_job.id) > before), (
            "no heartbeat ever landed"
        )

    assert heartbeat.beats >= 1


def test_a_job_that_is_taken_away_stops_the_beating(
    conn: psycopg.Connection,
    committed_job: AnalysisJob,
    settings_env: None,
) -> None:
    """Once the job is no longer in flight the thread has nothing left to say.

    This is the reap case: a worker that was too slow to report is assumed dead, and the
    thread it left behind has to notice rather than keep writing to a finished job.
    """
    heartbeat = Heartbeat(job_id=committed_job.id, interval_seconds=INTERVAL_SECONDS).start()
    try:
        running = analysis_job.get(conn, committed_job.id)
        assert running is not None
        queue.fail(conn, job=running, error_code="stale")
        conn.commit()

        assert _wait_until(lambda: heartbeat.lost), "the heartbeat never noticed"

        settled = heartbeat.beats
        time.sleep(INTERVAL_SECONDS * 4)
        assert heartbeat.beats == settled
    finally:
        heartbeat.stop()


def test_a_job_that_does_not_exist_is_not_an_error(settings_env: None) -> None:
    """A heartbeat for a row that is gone is a ``False``, not an exception."""
    heartbeat = Heartbeat(job_id=new_id(), interval_seconds=INTERVAL_SECONDS).start()
    try:
        assert _wait_until(lambda: heartbeat.lost), "the heartbeat never noticed"
        assert heartbeat.beats == 0
    finally:
        heartbeat.stop()


def test_a_database_that_is_unreachable_does_not_kill_the_job() -> None:
    """A blip is retried on the next tick: the job itself has to survive it.

    The lease is fifteen minutes and the interval is fifteen seconds, so several missed
    beats are expected to be harmless. Reporting one upward as a failure would abandon
    work that is still perfectly good.
    """

    @contextmanager
    def unreachable() -> Iterator[psycopg.Connection]:
        raise psycopg.OperationalError("no database today")

    heartbeat = Heartbeat(
        job_id=new_id(),
        interval_seconds=INTERVAL_SECONDS,
        connect=unreachable,
    ).start()
    try:
        time.sleep(INTERVAL_SECONDS * 3)
        assert heartbeat.beats == 0
        assert heartbeat.lost is False
    finally:
        # Reaching here at all is the assertion: an unreachable database did not take the
        # heartbeat - or the worker it belongs to - down with it.
        heartbeat.stop()


def _start(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    source_key: str,
) -> AnalysisJob:
    """Queue a job and start it, the way the pipeline's first transaction does."""
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version="0.1.0",
        source_object_key=source_key,
    )
    assert outcome.job is not None

    started = queue.begin(conn, job=outcome.job)
    assert started is not None
    return started


def _heartbeat_of(conn: psycopg.Connection, job_id: UUID) -> datetime | None:
    """Read the column the heartbeat writes, on this connection's latest snapshot."""
    row = conn.execute(
        "select heartbeat_at from public.analysis_jobs where id = %s",
        (job_id,),
    ).fetchone()
    return None if row is None else row["heartbeat_at"]


def _wait_until(condition: Callable[[], bool], *, timeout: float = WAIT_SECONDS) -> bool:
    """Poll for something another thread does, and give up rather than hang."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False
