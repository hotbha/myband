"""The analysis queue's state machine, against a real database.

Every case but one runs inside the rolled-back transaction the ``conn`` fixture
provides - possible because the service takes explicit timestamps, so a test can
put a heartbeat an hour in the past without touching the clock. The exception is
the SKIP LOCKED case, which has to commit and says so.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from app.core.db import connect
from app.models import analysis_job, analysis_result, song
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import ResultInput
from app.schemas.analysis_job import AnalysisJobOut
from app.services import queue

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

TEST_DATABASE_URL = os.environ.get("MYBAND_TEST_DATABASE_URL", "")
PIPELINE_VERSION = "0.1.0"


def _sample_results(object_key: str) -> list[ResultInput]:
    """One inline artifact and one that lives in R2."""
    return [
        ResultInput(kind="bpm", summary={"bpm": 128.0, "confidence": 0.94}),
        ResultInput(
            kind="midi",
            object_key=object_key,
            object_bytes=4096,
            object_content_type="audio/midi",
        ),
    ]


def _running_job(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    source_key: str,
) -> AnalysisJob:
    """Take a song from nothing to a running job, the way the dispatcher does."""
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=source_key,
    )
    assert outcome.created is True

    claimed = _claim_own_job(conn, song_id=song_id)
    dispatched = queue.mark_dispatched(conn, job=claimed, runpod_job_id="rp_test")
    assert dispatched is not None

    running = queue.mark_running(conn, job=dispatched)
    assert running is not None
    return running


def _claim_own_job(conn: psycopg.Connection, *, song_id: UUID) -> AnalysisJob:
    """Claim this song's job, whatever else the database happens to be holding.

    ``claim_next`` takes the *oldest* queued job in the table, and this suite shares a
    database with the seed and with everything uploaded to it since. A test that
    assumed the first claim was its own would take someone else's job and then assert
    about the wrong row.
    """
    for candidate in queue.claim_next(conn, limit=queue.MAX_BATCH):
        if candidate.song_id == song_id:
            return candidate

    raise AssertionError("no queued job for this song")


def test_enqueue_creates_one_job_per_song(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A second request for the same song returns the job already in flight."""
    source = make_object_key(name="source.wav")

    first = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=source,
    )
    second = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=source,
    )

    assert first.created is True
    assert first.job is not None
    assert first.job.status == "queued"
    assert second.created is False
    assert second.job is not None
    assert second.job.id == first.job.id
    assert len(analysis_job.list_for_song(conn, song_id)) == 1


def test_happy_path_reaches_succeeded(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """queued -> dispatched -> running -> succeeded, with artifacts and the pointer."""
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=make_object_key(name="source.wav"),
    )
    assert outcome.job is not None
    queued = outcome.job

    # `claim_next` hands back the oldest queued rows in the *table*, so this asks it
    # for this song's job rather than assuming it is the only one there - the database
    # may well be holding a real upload's queued job alongside it.
    claimed = _claim_own_job(conn, song_id=song_id)
    assert claimed.id == queued.id

    dispatched = queue.mark_dispatched(conn, job=claimed, runpod_job_id="rp_test_1")
    assert dispatched is not None
    assert dispatched.status == "dispatched"
    assert dispatched.attempts == 1
    assert dispatched.dispatched_at is not None

    running = queue.mark_running(conn, job=dispatched)
    assert running is not None
    assert running.status == "running"
    assert running.started_at is not None

    finished = queue.complete(
        conn,
        job=running,
        results=_sample_results(make_object_key(prefix="songs", name="analysis.mid")),
        compute_seconds=12.5,
    )

    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.finished_at is not None
    assert finished.error_code is None
    assert float(finished.compute_seconds) == pytest.approx(12.5)

    artifacts = analysis_result.list_for_job(conn, queued.id)
    assert [artifact.kind for artifact in artifacts] == ["bpm", "midi"]

    refreshed = song.get(conn, song_id)
    assert refreshed is not None
    assert refreshed.latest_job_id == queued.id


def test_a_stale_worker_cannot_overwrite_a_finished_job(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A worker that lost its job is told no, instead of clobbering the winner."""
    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )
    assert queue.complete(conn, job=job, results=[]) is not None

    # The copy the worker holds still says "running", which is the guard.
    assert queue.mark_running(conn, job=job) is None
    assert queue.fail(conn, job=job, error_code="worker_lost") is None
    assert queue.heartbeat(conn, job_id=job.id) is False


def test_fail_records_a_reason_and_is_terminal(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    failed = queue.fail(
        conn,
        job=job,
        error_code="decode_error",
        error_message="ffmpeg could not read the source object",
    )

    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "decode_error"
    assert failed.error_message is not None
    assert failed.finished_at is not None
    assert failed.attempts == 1
    assert queue.mark_running(conn, job=failed) is None


def test_reap_stale_fails_silent_jobs(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    # Alive: its heartbeat is now, so the sweep leaves it alone. The sweep is
    # global by design, so the assertion is about this job rather than about the
    # whole queue - whatever else the seed put in the table is not a fact about
    # this one.
    assert job.id not in {
        reaped_job.id for reaped_job in queue.reap_stale(conn, older_than=timedelta(minutes=15))
    }

    conn.execute(
        "update public.analysis_jobs set heartbeat_at = %s where id = %s",
        (datetime.now(UTC) - timedelta(hours=1), job.id),
    )

    reaped = {
        reaped_job.id: reaped_job
        for reaped_job in queue.reap_stale(conn, older_than=timedelta(minutes=15))
    }

    assert job.id in reaped
    assert reaped[job.id].status == "failed"
    assert reaped[job.id].error_code == "stale"
    assert reaped[job.id].finished_at is not None


def test_a_reaped_job_can_be_queued_again_as_a_new_row(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """Retrying never resurrects a job: the count and the history stay honest."""
    source = make_object_key(name="source.wav")
    job = _running_job(conn, user_id=user_id, song_id=song_id, source_key=source)
    conn.execute(
        "update public.analysis_jobs set heartbeat_at = %s where id = %s",
        (datetime.now(UTC) - timedelta(hours=1), job.id),
    )
    assert job.id in {
        reaped_job.id for reaped_job in queue.reap_stale(conn, older_than=timedelta(minutes=15))
    }

    requeued = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=source,
    )

    assert requeued.created is True
    assert requeued.job is not None
    assert requeued.job.id != job.id
    assert requeued.job.status == "queued"
    assert len(analysis_job.list_for_song(conn, song_id)) == 2


def test_the_usage_meter_counts_only_success(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """One billable unit is one job that reached succeeded - the failed try is free."""
    source = make_object_key(name="source.wav")

    doomed = _running_job(conn, user_id=user_id, song_id=song_id, source_key=source)
    queue.fail(conn, job=doomed, error_code="decode_error")

    good = _running_job(conn, user_id=user_id, song_id=song_id, source_key=source)
    assert queue.complete(conn, job=good, results=[]) is not None

    row = conn.execute(
        """
        select count(*) as billable
        from public.analysis_jobs
        where user_id = %s and status = 'succeeded' and finished_at is not null
        """,
        (user_id,),
    ).fetchone()

    assert row["billable"] == 1


def test_the_job_schema_maps_a_row(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The response contract reads the dataclass, and knows what is billable."""
    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    payload = AnalysisJobOut.model_validate(job)

    assert payload.id == job.id
    assert payload.song_id == song_id
    assert payload.status == "running"
    assert payload.is_terminal is False
    assert payload.is_billable is False


def test_a_second_dispatcher_skips_a_claimed_job(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The one case that commits: SKIP LOCKED is about what transactions hide.

    Dispatcher A claims the queued job and holds it. Dispatcher B, on its own
    connection, must find nothing even though the row is committed and queued.
    The cleanup deletes the song, which cascades to the job, so the database is
    left the way the seed wrote it.
    """
    try:
        queue.enqueue(
            conn,
            user_id=user_id,
            song_id=song_id,
            pipeline_version=PIPELINE_VERSION,
            source_object_key=make_object_key(name="source.wav"),
        )
        conn.commit()

        # Dispatcher A takes everything the queue is holding, so that B has nothing
        # left to find. The subject of this test is the lock, not the count: other
        # queued rows - the seed's, or a real upload's - would otherwise be B's.
        assert len(queue.claim_next(conn, limit=queue.MAX_BATCH)) >= 1

        with connect(url=TEST_DATABASE_URL) as other_dispatcher:
            # Plain FOR UPDATE would block here, so the timeout turns that
            # regression into a failure instead of a hung test run.
            other_dispatcher.execute("set local statement_timeout = '2s'")
            assert queue.claim_next(other_dispatcher) == []
    finally:
        conn.rollback()
        conn.execute("delete from public.songs where id = %s", (song_id,))
        conn.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()
