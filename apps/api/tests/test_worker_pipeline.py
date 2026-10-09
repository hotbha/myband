"""One job, from the queue to the rows, without audio or a bucket.

The stages are scripted and the store is in memory, so everything asserted here is the
pipeline's *own* behaviour: which job it takes, what it writes on success, and what it
refuses to write when the job has already moved on. The failures live next door, in
``test_worker_pipeline_failures.py``; a real recording through the real detectors is
``test_worker_e2e.py``.

Every case runs inside the rolled-back transaction the ``conn`` fixture provides - the
pipeline's own "transactions" are pointed at that same connection, so a write that should not
have happened fails an assertion instead of leaking into the next test.

Needs a migrated database; see ``test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from app.models import analysis_job, analysis_result, song
from app.workers import artifacts
from tests.fakes import FakeAnalysis, FakeObjectStore, FakeTranscription
from tests.worker_support import queued, worker

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)


# --- The happy path -----------------------------------------------------------


def test_a_queued_job_becomes_a_succeeded_job(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Claim, work, complete: the job row carries the timing and the attempt count."""
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)

    outcome = worker(conn, store).run_once()

    assert outcome is not None
    assert outcome.job_id == job.id
    assert outcome.status == "succeeded"
    assert outcome.error_code is None

    finished = analysis_job.get(conn, job.id)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.attempts == 1  # one dispatch, one billable unit
    assert finished.started_at is not None
    assert finished.heartbeat_at is not None
    assert finished.finished_at is not None
    assert finished.error_code is None
    # The duration the row records is the one the pipeline measured with its own clock - the
    # stepping clock is read three times: on claiming, before the stages, and on finishing -
    # and the outcome the runner sees says the same number.
    assert finished.compute_seconds is not None
    assert finished.compute_seconds > 0
    assert finished.compute_seconds == Decimal(str(outcome.seconds))


def test_the_song_carries_what_was_measured(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Duration, tempo and key land on the song, in the same transaction as the pointer."""
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)

    worker(conn, store).run_once()

    refreshed = song.get(conn, song_id)
    assert refreshed is not None
    assert refreshed.latest_job_id == job.id
    assert refreshed.duration_ms == FakeAnalysis().duration_ms
    assert refreshed.bpm == Decimal("120.00")
    assert refreshed.musical_key == "A minor"


def test_the_artifacts_describe_themselves(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Three kinds of row, and a MIDI object the row and the bucket agree about.

    The MIDI row's ``object_key`` satisfying ``analysis_results_object_key_check`` is part of
    the assertion: the insert would have been refused otherwise, so the key shape is verified
    against the database rather than against a copy of its regex.
    """
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)

    worker(conn, store).run_once()

    rows = {row.kind: row for row in analysis_result.list_for_job(conn, job.id)}
    assert set(rows) == {"bpm", "key", "midi"}

    assert rows["bpm"].summary == {"bpm": 120.0, "beats": 16}
    assert rows["key"].summary == {"key": "A minor", "strength": 0.9}

    midi = rows["midi"]
    assert midi.object_key == artifacts.midi_object_key(user_id=user_id, job_id=job.id)
    assert midi.object_bytes == len(FakeTranscription().data)
    assert midi.object_content_type == "audio/midi"
    assert midi.summary == {"notes": 3, "window_seconds": 30, "transcriber": "fake-transcriber"}
    assert store.download(object_key=midi.object_key) == FakeTranscription().data


def test_the_worker_returns_none_when_the_queue_is_empty(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    own_queue: None,
) -> None:
    """Nothing to claim is not an error: it is what an idle poll is."""
    assert worker(conn, store).run_once() is None


def test_a_second_pass_over_a_finished_job_writes_nothing(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """The same job offered twice writes one set of rows and one object.

    ``dataclasses.replace`` reproduces what the worker believed it held - a job it had
    started - after the row itself has moved on. The guarded transition is what refuses the
    second write, which is why none of this needs a flag or a lock.
    """
    job = queued(conn, store, user_id=user_id, song_id=song_id, make_object_key=make_object_key)
    pipeline = worker(conn, store)

    assert pipeline.run_once() is not None
    after_first = analysis_result.list_for_job(conn, job.id)

    finished = analysis_job.get(conn, job.id)
    assert finished is not None
    second = pipeline.process(replace(finished, status="running"))

    assert second.status == "lost"
    assert analysis_result.list_for_job(conn, job.id) == after_first
    assert len(store.bodies) == 2  # the source audio and one MIDI, not a second copy
    assert analysis_job.get(conn, job.id).finished_at == finished.finished_at
