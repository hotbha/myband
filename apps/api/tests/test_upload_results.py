"""What a completed upload leaves behind, and how it is read back.

A song does not carry its analysis status: ``songs.latest_job_id`` only moves when a
job *succeeds*, so a queued job - or one that failed - has to be answered from
``analysis_jobs``. These tests pin that down, along with the two things a completed
upload decides about the song: which project it is filed into, and what happens to
the job it queued.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from app.core.problems import ErrorCode
from app.models import analysis_job, project, song
from app.services import uploads
from tests.fakes import FakeObjectStore
from tests.support import TWO_KIB, complete, refused, start

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)


@pytest.fixture
def store() -> FakeObjectStore:
    """An object store that remembers what it was asked for."""
    return FakeObjectStore()


def _completed_upload(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> uploads.CompletedUpload:
    """Presign, "upload", and complete - the three moves a browser makes."""
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=TWO_KIB)
    return complete(conn, store, user_id, started.upload.id)


# --- Filing ------------------------------------------------------------------


def test_a_song_can_be_filed_into_the_callers_own_project(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    album = project.insert(conn, owner_id=user_id, name="Album")
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=TWO_KIB)

    outcome = complete(conn, store, user_id, started.upload.id, project_id=album.id)

    assert outcome.song.project_id == album.id


def test_a_song_cannot_be_filed_into_someone_elses_project(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    make_user: Callable[..., UUID],
) -> None:
    theirs = project.insert(conn, owner_id=make_user(), name="Not Yours")
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=TWO_KIB)

    problem = refused(complete, conn, store, user_id, started.upload.id, project_id=theirs.id)

    assert problem.status == 404
    assert problem.code is ErrorCode.PROJECT_NOT_FOUND
    assert song.list_for_user(conn, user_id) == []


def test_a_deleted_project_cannot_receive_a_song(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    gone = project.insert(conn, owner_id=user_id, name="Old Set")
    project.soft_delete(conn, project_id=gone.id)
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=TWO_KIB)

    problem = refused(complete, conn, store, user_id, started.upload.id, project_id=gone.id)

    assert problem.code is ErrorCode.PROJECT_NOT_FOUND


# --- What the song reports ---------------------------------------------------


def test_the_song_reports_the_job_that_is_in_flight(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    outcome = _completed_upload(conn, store, user_id)
    assert outcome.job is not None

    current = uploads.latest_job(conn, outcome.song.id)

    assert current is not None
    assert current.id == outcome.job.id
    assert current.status == "queued"


def test_a_failed_analysis_is_still_what_the_song_reports(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    """A failure never reaches ``songs.latest_job_id``, so the song has to be asked."""
    outcome = _completed_upload(conn, store, user_id)
    assert outcome.job is not None

    failed = analysis_job.transition(
        conn,
        job_id=outcome.job.id,
        expected_status="queued",
        status="failed",
        finished_at=datetime.now(UTC),
        error_code="decode_error",
        error_message="the upload is not decodable audio",
    )
    assert failed is not None

    current = uploads.latest_job(conn, outcome.song.id)

    assert current is not None
    assert current.id == outcome.job.id
    assert current.status == "failed"
    assert song.get(conn, outcome.song.id).latest_job_id is None


def test_the_library_asks_for_every_songs_active_job_in_one_query(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """`song_id` is a second song, owned by the same account, with no job at all."""
    outcome = _completed_upload(conn, store, user_id)

    active = analysis_job.list_active_for_songs(conn, [outcome.song.id, song_id])

    assert {job.song_id for job in active} == {outcome.song.id}
    assert analysis_job.list_active_for_songs(conn, []) == []
