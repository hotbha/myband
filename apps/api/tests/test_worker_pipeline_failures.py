"""What the worker writes when something goes wrong.

The mirror image of ``test_worker_pipeline.py``, which covers the job that works. Every case
here is a way to fail: a bucket that will not answer, a bucket that refuses outright, a
recording that is not there, a job that runs too long, a bug, and the two ways a job can be
taken away mid-flight. What each one has to get right is the *code* it leaves behind and the
rows it does not write - a job that fails with no reason is a page nobody can act on, and a
job that half-writes a result is a library that lies.
"""

import os
from collections.abc import Callable
from uuid import UUID

import psycopg
import pytest
from app.models import analysis_job, analysis_result, song
from app.services import queue
from app.workers.errors import FailureCode, PermanentError
from tests.fakes import FakeAnalysis, FakeObjectStore, ScriptedStage, SteppingClock
from tests.worker_support import RejectingStore, UnavailableStore, queued, tuning, worker

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)


def test_a_transient_failure_is_retried_with_a_growing_backoff(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A bucket that refuses twice and then answers: the job still succeeds."""
    store = UnavailableStore(failures=2)
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    slept: list[float] = []

    outcome = worker(
        conn,
        store,
        tuning=tuning(max_attempts=3, backoff_seconds=0.5),
        sleep=slept.append,
    ).run_once()

    assert outcome is not None
    assert outcome.status == "succeeded"
    assert slept == [0.5, 1.0]  # one backoff per retry, growing by the attempt number

    finished = analysis_job.get(conn, job.id)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.attempts == 1  # a retry is not a new dispatch, so not a new billable unit


def test_a_bucket_that_stays_down_fails_the_job_with_its_code(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Exhausting the retries fails the job with a stable code and a readable reason."""
    store = UnavailableStore(failures=99)
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    slept: list[float] = []

    outcome = worker(
        conn,
        store,
        tuning=tuning(max_attempts=2, backoff_seconds=1.0),
        sleep=slept.append,
    ).run_once()

    assert outcome is not None
    assert outcome.status == "failed"
    assert outcome.error_code == FailureCode.STORAGE_UNAVAILABLE
    assert slept == [1.0]  # one retry, then it gave up

    failed = analysis_job.get(conn, job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "storage_unavailable"
    assert failed.error_message == "storage is down"
    assert failed.finished_at is not None
    assert song.get(conn, song_id).bpm is None


def test_a_missing_recording_fails_before_anything_is_analysed(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """An object that is not in the bucket will not be there next time either."""
    job = queued(
        conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key, audio=None
    )
    analyzer = ScriptedStage(FakeAnalysis())

    outcome = worker(conn, store, analyze=analyzer).run_once()

    assert outcome is not None
    assert outcome.error_code == FailureCode.SOURCE_MISSING
    assert analyzer.calls == 0
    assert analysis_result.list_for_job(conn, job.id) == []


def test_a_job_that_overruns_its_budget_fails(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Time spent is what is checked, so a stepping clock overruns without waiting."""
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    analyzer = ScriptedStage(FakeAnalysis())

    outcome = worker(
        conn,
        store,
        analyze=analyzer,
        tuning=tuning(timeout_seconds=0.5),
        clock=SteppingClock(step=1.0),
    ).run_once()

    assert outcome is not None
    assert outcome.error_code == FailureCode.ANALYSIS_TIMEOUT
    assert analyzer.calls == 0

    failed = analysis_job.get(conn, job.id)
    assert failed is not None
    assert failed.status == "failed"


def test_a_bug_fails_the_job_instead_of_leaving_it_running(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Even an unhandled exception ends terminal, with the class named in the message."""
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)

    outcome = worker(conn, store, analyze=ScriptedStage(ValueError("boom"))).run_once()

    assert outcome is not None
    assert outcome.error_code == FailureCode.INTERNAL_ERROR
    assert outcome.error_message is not None
    assert "ValueError" in outcome.error_message

    failed = analysis_job.get(conn, job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.finished_at is not None


def test_a_bucket_that_refuses_the_artifact_fails_without_retrying(
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A 415 is a policy problem, not a blip: the job is failed once, with its own code.

    This is the failure that the end-to-end test found the hard way - a bucket whose
    ``allowed_mime_types`` did not list ``audio/midi`` - and the reason it has a code of its
    own: "storage_unavailable" would have sent whoever was on call looking for an outage, and
    the retries would have been three rounds of waiting for a policy that cannot change on its
    own.
    """
    store = RejectingStore()
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    slept: list[float] = []

    outcome = worker(
        conn,
        store,
        tuning=tuning(max_attempts=3, backoff_seconds=1.0),
        sleep=slept.append,
    ).run_once()

    assert outcome is not None
    assert outcome.status == "failed"
    assert outcome.error_code == FailureCode.STORAGE_REJECTED
    assert slept == []  # not one retry: waiting cannot make the bucket say yes

    failed = analysis_job.get(conn, job.id)
    assert failed is not None
    assert failed.error_code == "storage_rejected"
    assert analysis_result.list_for_job(conn, job.id) == []


def test_a_job_reaped_while_running_keeps_the_reapers_verdict(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A sweep took the job away. The work is discarded and the verdict stands.

    This is the case that makes ``lost`` a real answer rather than a defensive branch: the
    analysis succeeds, and every write it wanted to make is refused, because the row is no
    longer in the state this worker believed it was in.
    """
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    claimed = queue.begin(conn, job=job)
    assert claimed is not None
    queue.fail(conn, job=claimed, error_code="stale", error_message="no heartbeat")

    outcome = worker(conn, store).process(claimed)

    assert outcome.status == "lost"
    assert analysis_result.list_for_job(conn, job.id) == []
    assert song.get(conn, song_id).bpm is None
    assert song.get(conn, song_id).latest_job_id is None

    reaped = analysis_job.get(conn, job.id)
    assert reaped is not None
    assert reaped.status == "failed"
    assert reaped.error_code == "stale"  # not overwritten by this worker
    assert reaped.error_message == "no heartbeat"


def test_a_failure_after_the_job_moved_on_is_not_recorded(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """The worker's own failure is reported to the runner, and not written over a row.

    ``outcome`` is the only place it is visible, which is deliberate: the database holds the
    verdict of whoever owns the job, and two accounts of one job is how a library starts
    contradicting itself.
    """
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    claimed = queue.begin(conn, job=job)
    assert claimed is not None
    queue.fail(conn, job=claimed, error_code="stale")

    outcome = worker(
        conn,
        store,
        analyze=ScriptedStage(PermanentError(FailureCode.DECODE_ERROR, "not audio")),
    ).process(claimed)

    assert outcome.status == "lost"
    assert outcome.error_code == FailureCode.DECODE_ERROR
    assert analysis_job.get(conn, job.id).error_code == "stale"
