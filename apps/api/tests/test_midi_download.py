"""``GET /songs/{id}/midi``: the link, and every reason there is not one.

The route decides two things - whether this caller may have a link, and which object the
link is for - and then hands the signing to the store. These tests drive the real route,
the real queue and real SQL, with the store swapped for one that remembers what it was
asked for, so what is asserted is the object key, the expiry and the filename that would
have been signed.

The MIDI key is taken from ``workers.artifacts.midi_object_key`` rather than spelled out,
so this suite cannot pass while the route and the worker disagree about where an artifact
lives.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from app.api.deps import current_user_id
from app.api.routes import songs as songs_routes
from app.core.config import get_settings
from app.core.ids import new_id
from app.main import create_app
from app.models import song as song_model
from app.models.analysis_result import ResultInput
from app.services import queue
from app.services.storage import get_object_store
from app.workers.artifacts import midi_object_key
from fastapi.testclient import TestClient
from tests.fakes import FakeObjectStore
from tests.support import claim_own_job, reuse_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

PIPELINE_VERSION = "0.1.0"
MIDI_BYTES = 4096


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    settings_env: None,
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> Iterator[TestClient]:
    """The API on the test's transaction, signed in as ``user_id``."""
    monkeypatch.setattr(songs_routes, "connect", lambda **_: reuse_connection(conn))

    app = create_app()
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as test_client:
        yield test_client


def _song_with_title(conn: psycopg.Connection, *, user_id: UUID, title: str) -> UUID:
    """A song whose title is what this case is about."""
    row = conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, %s, %s)
        returning id
        """,
        (new_id(), user_id, title, f"users/{user_id}/uploads/{new_id()}/titled.wav"),
    ).fetchone()
    return row["id"]


def _analyse(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    source_key: str,
    with_midi: bool = True,
) -> UUID:
    """Take a song to a succeeded job the way the worker does, and return the job id.

    ``with_midi=False`` is the shape a future pipeline could produce: a job that finished
    and stored a tempo but no transcription. The route has to answer for that too, rather
    than signing a link to an object nobody wrote.
    """
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=source_key,
    )
    assert outcome.created is True

    running = queue.begin(conn, job=claim_own_job(conn, song_id=song_id))
    assert running is not None

    results = [ResultInput(kind="bpm", summary={"bpm": 128.0, "beats": 16})]
    if with_midi:
        results.append(
            ResultInput(
                kind="midi",
                summary={"notes": 3, "window_seconds": 30, "transcriber": "pYIN"},
                object_key=midi_object_key(user_id=user_id, job_id=running.id),
                object_bytes=MIDI_BYTES,
                object_content_type="audio/midi",
            )
        )

    finished = queue.complete(conn, job=running, results=results)
    assert finished is not None
    return finished.id


# --- The link -----------------------------------------------------------------


def test_an_analysed_song_hands_back_a_link_to_its_midi(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The link names the artifact's own key, and expires inside the configured TTL."""
    job_id = _analyse(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )
    expected_key = midi_object_key(user_id=user_id, job_id=job_id)

    response = client.get(f"/songs/{song_id}/midi")

    assert response.status_code == 200
    assert store.last_presigned_get["object_key"] == expected_key
    assert store.last_presigned_get["expires_in"] == 300

    body = response.json()
    assert body["url"].startswith("https://bucket.test/")
    assert expected_key in body["url"]

    remaining = (datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC)).total_seconds()
    assert 0 < remaining <= get_settings().download_url_ttl_seconds


def test_a_song_nobody_has_analysed_signs_nothing(
    client: TestClient,
    store: FakeObjectStore,
    song_id: UUID,
) -> None:
    """No link to hand out, and no signature spent finding that out."""
    response = client.get(f"/songs/{song_id}/midi")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "analysis_not_ready",
        "message": "This song has not been analysed yet.",
    }
    assert store.presigned_gets == []


def test_a_succeeded_job_without_a_midi_signs_nothing(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A finished analysis is not the same as a MIDI: ``latest_job_id`` is set either way."""
    _analyse(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
        with_midi=False,
    )

    response = client.get(f"/songs/{song_id}/midi")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song's analysis produced no MIDI file."
    assert store.presigned_gets == []


# --- Refusals -----------------------------------------------------------------


def test_an_unknown_song_is_not_found(client: TestClient, store: FakeObjectStore) -> None:
    response = client.get(f"/songs/{new_id()}/midi")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.presigned_gets == []


def test_somebody_elses_song_is_not_found(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    make_user: Callable[..., UUID],
) -> None:
    """Ownership is checked before anything is signed: a 404, and no link."""
    theirs = make_user()
    row = conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, 'Theirs', %s)
        returning id
        """,
        (new_id(), theirs, f"users/{theirs}/uploads/{new_id()}/theirs.wav"),
    ).fetchone()

    response = client.get(f"/songs/{row['id']}/midi")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.presigned_gets == []


def test_a_soft_deleted_song_is_not_found(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    song_id: UUID,
) -> None:
    """A deleted song is answered like one that never existed, not with a link."""
    assert song_model.soft_delete(conn, song_id=song_id) is True

    response = client.get(f"/songs/{song_id}/midi")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.presigned_gets == []


def test_a_request_without_a_token_is_refused(
    store: FakeObjectStore,
    settings_env: None,
) -> None:
    """Signing a download link needs a caller, like every other route."""
    app = create_app()
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as anonymous:
        response = anonymous.get(f"/songs/{new_id()}/midi")

    assert response.status_code == 401
    assert store.presigned_gets == []


# --- The name the browser saves -----------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Midnight Drive", "Midnight_Drive.mid"),
        ('Chaos "song"', "Chaos__song.mid"),
        ("two\nlines", "two_lines.mid"),
        ('""', "transcription.mid"),
    ],
)
def test_the_saved_name_comes_from_the_title_and_survives_a_hostile_one(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    title: str,
    expected: str,
) -> None:
    """A quote or a newline in a title never reaches the header it becomes."""
    song_id = _song_with_title(conn, user_id=user_id, title=title)
    _analyse(
        conn,
        user_id=user_id,
        song_id=song_id,
        source_key=f"users/{user_id}/uploads/{new_id()}/source.wav",
    )

    assert client.get(f"/songs/{song_id}/midi").status_code == 200
    assert store.last_presigned_get["filename"] == expected
