"""The upload lifecycle, against a real database.

``FakeObjectStore`` stands in for R2, so these tests walk the whole path the
browser walks - presign, the object arriving, completion, the song, the queued job
- without a bucket or a network call. The database is real, and every row is rolled
back by the ``conn`` fixture, so the suite leaves it exactly as the seed wrote it.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from app.core.config import get_settings
from app.core.problems import ErrorCode
from app.models import analysis_job, song
from app.models import upload as upload_model
from app.services import upload_rules
from tests.fakes import PRESIGN_BASE_URL, FakeObjectStore
from tests.support import complete, refused, start

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)


@pytest.fixture
def store() -> FakeObjectStore:
    """An object store that remembers what it was asked for."""
    return FakeObjectStore()


# --- Presign -----------------------------------------------------------------


def test_presign_writes_a_pending_row_and_a_url_for_that_row(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    settings_env: None,
) -> None:
    started = start(
        conn,
        store,
        user_id,
        filename="midnight drive.mp3",
        declared_bytes=2048,
        checksum_sha256="A" * 64,
    )
    row = started.upload

    assert row.status == "pending"
    assert row.song_id is None
    assert row.user_id == user_id
    assert row.declared_bytes == 2048
    assert row.declared_content_type == "audio/mpeg"
    assert row.checksum_expected == "a" * 64

    # The key the URL was signed for is the key on the row, and it sits inside the
    # caller's own prefix - the row's CHECK constraint agreed with all of that.
    assert row.object_key == f"users/{user_id}/uploads/{row.id}/midnight_drive.mp3"
    assert store.last_presigned["object_key"] == row.object_key
    assert store.last_presigned["content_type"] == "audio/mpeg"
    assert store.last_presigned["expires_in"] == get_settings().upload_url_ttl_seconds
    assert started.upload_url.startswith(f"{PRESIGN_BASE_URL}/{row.object_key}?")

    # The URL and the row expire together.
    ttl = get_settings().upload_url_ttl_seconds
    remaining = row.expires_at - datetime.now(UTC)
    assert timedelta(seconds=ttl - 30) < remaining <= timedelta(seconds=ttl + 30)


def test_presign_refuses_a_file_type_the_product_does_not_take(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    problem = refused(
        start,
        conn,
        store,
        user_id,
        filename="track.flac",
        content_type="audio/flac",
    )

    assert problem.status == 415
    # Nothing was written for this caller: no row exists, so no URL was ever handed
    # out. (Scoped to the account - the seed has uploads of its own.)
    assert (
        conn.execute(
            "select count(*) as n from public.uploads where user_id = %s", (user_id,)
        ).fetchone()["n"]
        == 0
    )


# --- Complete ----------------------------------------------------------------


def test_completing_an_upload_creates_the_song_the_claim_and_a_queued_job(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    settings_env: None,
) -> None:
    started = start(conn, store, user_id, checksum_sha256="b" * 64)
    store.put(started.upload.object_key, body_bytes=4096, content_type="audio/mpeg")

    outcome = complete(
        conn,
        store,
        user_id,
        started.upload.id,
        title="Midnight Drive",
        artist="The Tests",
    )

    assert outcome.created is True
    assert outcome.upload.status == "completed"
    assert outcome.upload.bytes_actual == 4096
    assert outcome.upload.content_type_actual == "audio/mpeg"
    assert outcome.upload.etag_actual == "5d41402abc4b2a76b9719d911017c592"
    assert outcome.upload.completed_at is not None
    assert outcome.upload.song_id == outcome.song.id

    assert outcome.song.title == "Midnight Drive"
    assert outcome.song.artist == "The Tests"
    assert outcome.song.source_object_key == started.upload.object_key
    assert outcome.song.source_bytes == 4096
    assert outcome.song.source_content_type == "audio/mpeg"
    assert outcome.song.source_checksum == "b" * 64
    # Only the queue service sets this, and only once a job succeeds.
    assert outcome.song.latest_job_id is None

    assert outcome.job is not None
    assert outcome.job.status == "queued"
    assert outcome.job.song_id == outcome.song.id
    assert outcome.job.source_object_key == started.upload.object_key
    assert outcome.job.pipeline_version == get_settings().pipeline_version


def test_a_song_is_named_after_the_file_when_no_title_is_given(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    started = start(conn, store, user_id, filename="Little Wing.wav", content_type="audio/wav")
    store.put(started.upload.object_key, body_bytes=1024, content_type="audio/wav")

    outcome = complete(conn, store, user_id, started.upload.id)

    assert outcome.song.title == "Little_Wing"


def test_completing_the_same_upload_twice_reports_the_first_result(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=2048)

    first = complete(conn, store, user_id, started.upload.id)
    second = complete(conn, store, user_id, started.upload.id)

    assert second.created is False
    assert second.song.id == first.song.id
    assert first.job is not None
    assert second.job is not None
    assert second.job.id == first.job.id
    assert len(analysis_job.list_for_song(conn, first.song.id)) == 1
    assert len(song.list_for_user(conn, user_id)) == 1


def test_completion_refuses_an_object_that_never_arrived(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    started = start(conn, store, user_id)

    problem = refused(complete, conn, store, user_id, started.upload.id)

    assert problem.status == 409
    assert problem.code is ErrorCode.OBJECT_NOT_FOUND
    assert upload_model.get(conn, started.upload.id).status == "pending"
    assert song.list_for_user(conn, user_id) == []


def test_completion_refuses_an_object_that_is_over_the_cap(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    """The declared size said 2 KiB; the object that landed says otherwise."""
    started = start(conn, store, user_id, declared_bytes=2048)
    store.put(started.upload.object_key, body_bytes=upload_rules.MAX_UPLOAD_BYTES + 1)

    problem = refused(complete, conn, store, user_id, started.upload.id)

    assert problem.status == 413
    assert problem.code is ErrorCode.FILE_TOO_LARGE
    assert upload_model.get(conn, started.upload.id).status == "pending"
    assert song.list_for_user(conn, user_id) == []


def test_completion_refuses_an_object_that_is_not_audio(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> None:
    started = start(conn, store, user_id)
    store.put(started.upload.object_key, body_bytes=2048, content_type="application/zip")

    problem = refused(complete, conn, store, user_id, started.upload.id)

    assert problem.status == 415
    assert problem.code is ErrorCode.UNSUPPORTED_MEDIA_TYPE
    assert song.list_for_user(conn, user_id) == []
