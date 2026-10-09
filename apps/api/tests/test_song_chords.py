"""``GET /songs/{id}/chords``: the timeline, and every reason there is not one.

The route decides two things - whether this caller may see the song's chords, and which object holds
them - and then reads that object itself, because the payload *is* the answer. These tests drive the
real route, the real queue and real SQL, with the store swapped for one that remembers what it was
asked for, so what is asserted is the body a browser would receive.

The chords key is taken from ``workers.artifacts.chords_object_key`` rather than spelled out, so
this suite cannot pass while the route and the worker disagree about where a timeline lives. The
rows are built by ``workers.artifacts.build_results``, so the digest asserted here is the one a real
job writes.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable, Iterator
from uuid import UUID

import psycopg
import pytest
from app.api.deps import current_user_id
from app.api.routes import songs as songs_routes
from app.core.ids import new_id
from app.main import create_app
from app.models import analysis_result
from app.models import song as song_model
from app.services import queue
from app.services.storage import get_object_store
from app.workers import artifacts
from fastapi.testclient import TestClient
from tests.fakes import (
    FakeAnalysis,
    FakeChordSegment,
    FakeChordTimeline,
    FakeObjectStore,
    FakeTranscription,
)
from tests.support import claim_own_job, reuse_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

PIPELINE_VERSION = "0.1.0"

# The timeline a finished job stored: one second of nothing, then four seconds of A minor. The
# no-chord segment is there on purpose - it is the case a digest is easiest to get wrong.
TIMELINE = FakeChordTimeline(
    segments=(
        FakeChordSegment(start_ms=0, end_ms=1000, chord="N", confidence=0.2),
        FakeChordSegment(start_ms=1000, end_ms=5000, chord="Am", confidence=0.91),
    ),
    key="A minor",
)


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


def _analyse(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    *,
    user_id: UUID,
    song_id: UUID,
    source_key: str,
    with_chords: bool = True,
    with_object: bool = True,
) -> UUID:
    """Take a song to a succeeded job the way the worker does, and return the job id.

    ``with_chords=False`` is what a job analysed before this artifact existed produces.
    ``with_object`` is what the seed leaves behind: a chords row whose object was never uploaded,
    which the route has to answer for rather than fail on.
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

    rows = artifacts.build_results(
        analysis=FakeAnalysis(),
        midi=artifacts.store_midi(
            store,
            user_id=user_id,
            job_id=running.id,
            transcription=FakeTranscription(),
        ),
        chords=artifacts.store_chords(
            store,
            user_id=user_id,
            job_id=running.id,
            timeline=TIMELINE,
        ),
    )

    if not with_object:
        key = artifacts.chords_object_key(user_id=user_id, job_id=running.id)
        store.bodies.pop(key, None)
        store.objects.pop(key, None)

    if not with_chords:
        rows = [row for row in rows if row.kind != "chords"]

    finished = queue.complete(conn, job=running, results=rows)
    assert finished is not None
    return finished.id


# --- The timeline -------------------------------------------------------------


def test_an_analysed_song_hands_back_its_chord_timeline(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The timeline itself, and not a link to it: this is a screen's read, not a download."""
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    response = client.get(f"/songs/{song_id}/chords")

    assert response.status_code == 200
    body = response.json()
    assert body["detector"] == "fake-chord-detector"
    assert body["vocabulary"] == "1.0"
    assert body["key"] == "A minor"
    assert body["hop_ms"] == 93
    assert body["segments"] == [
        {"start_ms": 0, "end_ms": 1000, "chord": "N", "confidence": 0.2},
        {"start_ms": 1000, "end_ms": 5000, "chord": "Am", "confidence": 0.91},
    ]

    # Not a presigned link, and nothing that expires - the one way this differs from the MIDI route.
    assert "url" not in body
    assert "expires_at" not in body
    assert store.presigned_gets == []
    # And no second copy of a number that belongs to the song rather than to the artifact.
    assert "duration_ms" not in body


def test_the_summary_is_the_stored_row_and_not_a_recomputation(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """One digest, written once by the worker: the response reports exactly what the row holds."""
    job_id = _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    row = analysis_result.get_for_job_kind(conn, job_id=job_id, kind="chords")
    assert row is not None

    body = client.get(f"/songs/{song_id}/chords").json()

    assert body["summary"] == row.summary
    assert body["summary"]["progression"] == ["Am"]
    assert body["summary"]["segments"] == 2
    assert body["summary"]["no_chord_ratio"] == 0.2
    # The key is in the digest as well as in the timeline, so a library row is readable on its own.
    assert body["summary"]["key"] == "A minor"


# --- Refusals -----------------------------------------------------------------


def test_a_song_that_has_never_been_analysed_is_not_ready(
    client: TestClient,
    store: FakeObjectStore,
    user_id: UUID,
    song_id: UUID,
) -> None:
    """The ``song_id`` fixture is a song with no job at all."""
    response = client.get(f"/songs/{song_id}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song has not been analysed yet."
    assert store.bodies == {}


def test_a_job_that_produced_no_chords_is_not_ready(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A job that finished and stored a tempo but no timeline, which is not an error."""
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
        with_chords=False,
    )

    response = client.get(f"/songs/{song_id}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song's analysis produced no chords."


def test_chords_whose_object_is_gone_are_not_ready(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The row exists and the bucket does not hold the object - the seed's own shape.

    A demo row written for a fixture nobody uploaded, and equally a real object swept before its
    row. Answered rather than crashed on, and answered in the same shape as the other two.
    """
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
        with_object=False,
    )

    response = client.get(f"/songs/{song_id}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song's chords are no longer in storage."


def test_an_unknown_song_is_not_found(client: TestClient, store: FakeObjectStore) -> None:
    response = client.get(f"/songs/{new_id()}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.bodies == {}


def test_somebody_elses_song_is_not_found(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    make_user: Callable[..., UUID],
) -> None:
    """Ownership is checked before the object is read: a 404, and nothing fetched."""
    theirs = make_user()
    row = conn.execute(
        """
        insert into public.songs (id, user_id, title, source_object_key)
        values (%s, %s, 'Theirs', %s)
        returning id
        """,
        (new_id(), theirs, f"users/{theirs}/uploads/{new_id()}/theirs.wav"),
    ).fetchone()

    response = client.get(f"/songs/{row['id']}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.bodies == {}


def test_a_soft_deleted_song_is_not_found(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    song_id: UUID,
) -> None:
    """A deleted song is answered like one that never existed, not with its chords."""
    assert song_model.soft_delete(conn, song_id=song_id) is True

    response = client.get(f"/songs/{song_id}/chords")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"


def test_a_request_without_a_token_is_refused(
    store: FakeObjectStore,
    settings_env: None,
) -> None:
    """Reading a timeline needs a caller, like every other route."""
    app = create_app()
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as anonymous:
        response = anonymous.get(f"/songs/{UUID(int=0)}/chords")

    assert response.status_code == 401
    assert store.bodies == {}
