"""A batch of uploads, through the queue, as one unit of work.

Nobody uploads one song; they upload an afternoon's worth. This module is about what the
queue guarantees when it is holding many jobs rather than the single one the state-machine
suite drives: that a dispatcher loop hands each job out exactly once, that one song's
failure does not stop the others, that a dead worker costs one row rather than the batch,
and that two dispatchers racing over the same batch never hand the same job to two workers.

Every case but the last runs inside the transaction the ``conn`` fixture rolls back, with
``own_queue`` cancelling whatever else the queue was holding so that the batch is the only
work there is. The last case has to commit - SKIP LOCKED is about what one transaction
hides from another - and takes the rest of the queue out of the way by claiming it on its
own connection, without dispatching any of it, so the database ends the test the way the
seed wrote it.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from uuid import UUID

import psycopg
import pytest
from app.core.db import connect
from app.core.ids import new_id
from app.models import analysis_job, analysis_result, song
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import ResultInput
from app.services import queue

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

TEST_DATABASE_URL = os.environ.get("MYBAND_TEST_DATABASE_URL", "")
PIPELINE_VERSION = "0.1.0"

# Enough jobs to need several claims and to leave room for two dispatchers to interleave,
# few enough to stay a test: these cases are about the shape of the work, not its volume.
BATCH = 12

# What each dispatcher asks for at a time, and the timeout on the cross-connection case.
CLAIM_LIMIT = 2
DISPATCHER_TIMEOUT_SECONDS = 60


def _results(object_key: str) -> list[ResultInput]:
    """What a worker stores for one song: a headline inline, the MIDI file in the bucket."""
    return [
        ResultInput(kind="bpm", summary={"bpm": 128.0, "confidence": 0.94}),
        ResultInput(
            kind="midi",
            object_key=object_key,
            object_bytes=4096,
            object_content_type="audio/midi",
        ),
    ]


def _enqueue(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    uploaded: song.Song,
) -> AnalysisJob:
    """Queue the analysis for one song, refusing to pretend a duplicate was a job."""
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=uploaded.id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=uploaded.source_object_key,
    )
    assert outcome.created is True, "the song already had work in flight"
    assert outcome.job is not None
    return outcome.job


def _batch(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    make_object_key: Callable[..., str],
    count: int = BATCH,
) -> list[AnalysisJob]:
    """``count`` songs, each with one queued job: an afternoon of uploads, in one transaction.

    A song and its job per iteration, so the batch is built exactly the way the upload flow
    builds it - one song, one job - and each job carries its own song's object key.

    The jobs share a ``created_at`` (``now()`` is the transaction's start time, not the
    statement's), so nothing here may assume an order within the batch. ``claim_next`` is
    oldest-first, which is what drains it; *which* of these is oldest is not defined.
    """
    jobs: list[AnalysisJob] = []
    for index in range(count):
        uploaded = song.insert(
            conn,
            user_id=user_id,
            title=f"Batch track {index + 1}",
            source_object_key=make_object_key(name=f"track-{index + 1}.wav"),
        )
        jobs.append(_enqueue(conn, user_id=user_id, uploaded=uploaded))
    return jobs


def _finish(
    conn: psycopg.Connection,
    *,
    job: AnalysisJob,
    object_key: str,
) -> AnalysisJob:
    """Drive one claimed job to succeeded, the way a dispatcher and a worker do."""
    dispatched = queue.mark_dispatched(conn, job=job, runpod_job_id=f"rp_{job.id}")
    assert dispatched is not None, "the claimed job was no longer queued"
    running = queue.mark_running(conn, job=dispatched)
    assert running is not None
    finished = queue.complete(
        conn,
        job=running,
        results=_results(object_key),
        compute_seconds=1.5,
    )
    assert finished is not None
    return finished


def _retry(conn: psycopg.Connection, *, job: AnalysisJob) -> AnalysisJob:
    """Queue the same song again, which is what a retry is: a new row."""
    source = song.get(conn, job.song_id)
    assert source is not None
    return _enqueue(conn, user_id=source.user_id, uploaded=source)


def _count(conn: psycopg.Connection, job_ids: list[UUID], *, status: str) -> int:
    """How many of these jobs are in ``status``."""
    row = conn.execute(
        """
        select count(*) as jobs
        from public.analysis_jobs
        where id = any(%s) and status = %s
        """,
        (job_ids, status),
    ).fetchone()
    return row["jobs"]


def _statuses(conn: psycopg.Connection, job_ids: list[UUID]) -> set[str]:
    """The statuses these jobs are in, as a set, for a one-line assertion."""
    return {analysis_job.get(conn, job_id).status for job_id in job_ids}


def _committed_batch(owner: psycopg.Connection, user: UUID) -> set[UUID]:
    """``BATCH`` songs with a queued job each, committed so other connections can see them.

    This is what the racing dispatchers race over. It is built outside the transaction the
    module's other cases roll back - the dispatchers only pick up committed work - which is
    why the songs it makes are deleted instead of rolled back.
    """
    expected: set[UUID] = set()
    for index in range(BATCH):
        key = f"users/{user}/uploads/{new_id()}/track-{index + 1}.wav"
        uploaded = song.insert(
            owner,
            user_id=user,
            title=f"Raced track {index + 1}",
            source_object_key=key,
        )
        expected.add(_enqueue(owner, user_id=user, uploaded=uploaded).id)
    owner.commit()
    return expected


def _race_two_dispatchers(owner: psycopg.Connection, *, expected: set[UUID]) -> None:
    """Run two dispatcher loops against one batch, then assert what they did to it.

    Exactness is asserted rather than a split: one dispatcher may legitimately win the whole
    batch, and which one does is scheduling, not a property of the queue.
    """
    start = Barrier(2)
    taken: list[list[UUID]] = [[], []]
    failures: list[BaseException] = []

    def dispatch(index: int) -> None:
        """One dispatcher's loop, until the batch is taken or nothing of it is left."""
        try:
            with connect(url=TEST_DATABASE_URL) as dispatcher:
                # Plain FOR UPDATE would block here; the timeout turns that regression into
                # a failure instead of a hung test run.
                dispatcher.execute("set local statement_timeout = '5s'")
                start.wait(timeout=10)
                while True:
                    mine = [
                        job
                        for job in queue.claim_next(dispatcher, limit=CLAIM_LIMIT)
                        if job.id in expected
                    ]
                    if not mine:
                        break
                    for job in mine:
                        dispatched = queue.mark_dispatched(
                            dispatcher,
                            job=job,
                            runpod_job_id=f"rp_{index}_{job.id}",
                        )
                        assert dispatched is not None, "another dispatcher had it"
                    # Committing is what makes the handoff real: the job leaves the queue and
                    # the lock it was claimed with goes with the transaction.
                    dispatcher.commit()
                    taken[index].extend(job.id for job in mine)
        except BaseException as cause:  # a thread's failure is reported by the caller
            failures.append(cause)

    dispatchers = [Thread(target=dispatch, args=(index,), daemon=True) for index in range(2)]
    for dispatcher in dispatchers:
        dispatcher.start()
    for dispatcher in dispatchers:
        dispatcher.join(timeout=DISPATCHER_TIMEOUT_SECONDS)

    assert not failures, f"a dispatcher gave up: {failures[0]!r}"
    assert all(not dispatcher.is_alive() for dispatcher in dispatchers), "still running"

    handed_out = taken[0] + taken[1]
    assert len(handed_out) == len(set(handed_out)), "two dispatchers took the same job"
    assert set(handed_out) == expected
    # Every job left the queue exactly once, so the batch is no longer a dispatcher's to pick
    # up...
    assert _statuses(owner, sorted(expected)) == {"dispatched"}
    # ...as a first attempt each: nobody was handed the same work twice.
    assert {analysis_job.get(owner, job_id).attempts for job_id in expected} == {1}


def test_a_batch_drains_to_succeeded(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Every song in the batch ends up analysed, with its artifacts and its pointer set.

    The loop is a dispatcher's: claim a few, hand them to workers, come back for more. What
    it proves is what a user sees afterwards - each song has exactly one row, a finished one,
    pointing at the analysis of *that* song.
    """
    jobs = _batch(conn, user_id=user_id, make_object_key=make_object_key)

    claimed: list[AnalysisJob] = []
    while True:
        batch = queue.claim_next(conn, limit=5)
        if not batch:
            break
        # A claim hands back at most what it was asked for: a dispatcher's batch is bounded.
        assert len(batch) <= 5
        claimed.extend(
            _finish(conn, job=job, object_key=make_object_key(name="sketch.mid")) for job in batch
        )

    assert {job.id for job in claimed} == {job.id for job in jobs}

    for job in jobs:
        assert analysis_job.get(conn, job.id).status == "succeeded"
        # One job per song, and it is the finished one.
        assert len(analysis_job.list_for_song(conn, job.song_id)) == 1
        assert song.get(conn, job.song_id).latest_job_id == job.id
        # What the MIDI download route reads, for every song in the batch.
        assert analysis_result.get_for_job_kind(conn, job_id=job.id, kind="midi") is not None

    # Drained: a dispatcher asking again now would idle rather than pick up more work.
    assert queue.claim_next(conn, limit=queue.MAX_BATCH) == []


def test_a_dispatcher_loop_hands_every_job_out_exactly_once(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Batched claims take the batch apart once: nothing skipped, nothing handed out twice.

    A job in two claims is two workers on one song. Its status is what refuses the second
    handoff - ``mark_dispatched`` returns ``None`` - and the count at the end is what refuses
    a job that was quietly never handed out at all, which is the failure a batch would hide.
    """
    jobs = _batch(conn, user_id=user_id, make_object_key=make_object_key, count=8)

    handed_out: list[UUID] = []
    while True:
        batch = queue.claim_next(conn, limit=3)
        if not batch:
            break
        for job in batch:
            assert job.id not in handed_out, "the same job was handed to two workers"
            dispatched = queue.mark_dispatched(conn, job=job, runpod_job_id=f"rp_{job.id}")
            assert dispatched is not None
            handed_out.append(job.id)

    assert set(handed_out) == {job.id for job in jobs}
    assert len(handed_out) == len(set(handed_out))
    # Every job is out of the dispatcher's hands and in a worker's, waiting to be started.
    assert _statuses(conn, handed_out) == {"dispatched"}


def test_one_song_failing_does_not_stop_the_batch(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A batch is not all-or-nothing: a decoder refusing one file leaves the rest alone."""
    jobs = _batch(conn, user_id=user_id, make_object_key=make_object_key, count=6)
    doomed, rest = jobs[0], jobs[1:]

    claimed = queue.claim_next(conn, limit=len(jobs))
    assert {job.id for job in claimed} == {job.id for job in jobs}

    dispatched = queue.mark_dispatched(conn, job=doomed, runpod_job_id="rp_doomed")
    assert dispatched is not None
    failed = queue.fail(
        conn,
        job=dispatched,
        error_code="decode_error",
        error_message="the decoder refused this file",
    )
    assert failed is not None
    assert failed.status == "failed"

    for job in rest:
        _finish(conn, job=job, object_key=make_object_key(name="sketch.mid"))

    # Everything else finished, each song pointing at its own job.
    assert _count(conn, [job.id for job in jobs], status="succeeded") == len(rest)
    for job in rest:
        assert song.get(conn, job.song_id).latest_job_id == job.id

    # The failure is terminal, keeps its reason, cost one attempt, and was not retried behind
    # the user's back; the song is left unanalysed rather than half-analysed.
    stored = analysis_job.get(conn, doomed.id)
    assert stored.error_code == "decode_error"
    assert stored.attempts == 1
    assert song.get(conn, doomed.song_id).latest_job_id is None
    assert analysis_result.list_for_job(conn, doomed.id) == []


def test_a_dead_worker_costs_one_row_not_the_batch(
    conn: psycopg.Connection,
    user_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """A worker that stops reporting is reaped, and the rest of the batch is untouched.

    All three jobs are handed out; one worker never says another word. The sweep fails that
    row - never billable - while the two jobs still queued in the same batch are not its
    business: ``queued`` is not a state a worker holds, so its age is not evidence that
    anything went wrong. The retry that follows is a new row, and the interrupted batch
    still drains.
    """
    jobs = _batch(conn, user_id=user_id, make_object_key=make_object_key, count=3)
    started = datetime.now(UTC)

    claimed = queue.claim_next(conn, limit=len(jobs))
    assert {job.id for job in claimed} == {job.id for job in jobs}

    gone = jobs[1]
    assert queue.mark_dispatched(conn, job=gone, runpod_job_id="rp_gone", at=started) is not None

    reaped = queue.reap_stale(conn, at=started + queue.STALE_AFTER + timedelta(seconds=1))

    assert {job.id for job in reaped} == {gone.id}
    assert analysis_job.get(conn, gone.id).error_code == analysis_job.STALE_ERROR_CODE

    # What the queue is left holding: the two jobs nobody was handed, exactly as they were.
    others = [job.id for job in jobs if job.id != gone.id]
    assert _statuses(conn, others) == {"queued"}

    # A retry is a new row, it converges, and the song never holds two jobs at once.
    retry = _retry(conn, job=gone)
    assert retry.id != gone.id
    _finish(conn, job=retry, object_key=make_object_key(name="sketch.mid"))

    assert len(analysis_job.list_for_song(conn, gone.song_id)) == 2
    assert song.get(conn, gone.song_id).latest_job_id == retry.id

    # And the batch the dead worker interrupted still finishes.
    for job in claimed:
        if job.id != gone.id:
            _finish(conn, job=job, object_key=make_object_key(name="sketch.mid"))
    assert _count(conn, [job.id for job in jobs], status="succeeded") == 2


def test_two_dispatchers_sharing_a_batch_never_hand_out_a_job_twice(
    conn: psycopg.Connection,
    make_user: Callable[..., UUID],
) -> None:
    """The one case that commits: two connections racing over the same batch.

    SKIP LOCKED is about what one transaction hides from another, so this cannot run inside
    the rolled-back transaction the rest of the module uses. It takes the queue that already
    exists out of the way differently: this test's own connection claims whatever is queued
    at the start - locking it for the duration, without dispatching any of it - so the two
    dispatchers, on their own connections, see this batch and nothing else. The ``finally``
    below rolls that claim back and deletes the songs created here, so the database ends the
    test the way the seed wrote it.

    Exactness is asserted rather than a split: one dispatcher may legitimately win the whole
    batch, and which one does is scheduling, not a property of the queue.
    """
    # Locked by this transaction until it rolls back: the seed's backlog, if it has one, is
    # not a dispatcher's to hand out while this test runs.
    _queued_before = queue.claim_next(conn, limit=queue.MAX_BATCH)

    user: UUID | None = None
    try:
        # The dispatchers are separate connections, so the batch has to be committed - and
        # therefore visible to them - before they start.
        with connect(url=TEST_DATABASE_URL) as owner:
            user = make_user(on=owner)
            _race_two_dispatchers(owner, expected=_committed_batch(owner, user))
    finally:
        # Releases the queue this test held, and leaves nothing of its own behind: the songs
        # it created are deleted, and the jobs cascade with them.
        conn.rollback()
        if user is not None:
            conn.execute("delete from public.songs where user_id = %s", (user,))
            conn.execute("delete from auth.users where id = %s", (user,))
            conn.commit()
