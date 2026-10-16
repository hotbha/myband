"""``GET /songs/{id}/sections``: the list, and every reason there is not one.

The route decides two things - whether this caller may see the song's sections, and which object
holds them - and then reads that object itself, because the payload *is* the answer. These tests
drive the real route, the real queue and real SQL, with the store swapped for one that remembers
what it was asked for, so what is asserted is the body a browser would receive.

The sections key is taken from ``workers.artifacts.sections_object_key`` rather than spelled out,
so this suite cannot pass while the route and the worker disagree about where a list lives. The
rows are built by ``workers.artifacts.build_results``, so the digest asserted here is the one a
real job writes.

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
from app.services import queue
from app.services.storage import get_object_store
from app.workers import artifacts
from fastapi.testclient import TestClient
from tests.fakes import (
    FakeAnalysis,
    FakeChordTimeline,
    FakeObjectStore,
    FakeSection,
    FakeSectionTimeline,
    FakeTranscription,
)
from tests.support import claim_own_job, reuse_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

PIPELINE_VERSION = "0.1.0"

# The list a finished job stored: A, B, A. The repeat is there on purpose - it is what makes the
# form a form, and it is the case a digest is easiest to get wrong.
SECTION_LIST = FakeSectionTimeline(
    sections=(
        FakeSection(start_ms=0, end_ms=6000, label="A", confidence=0.91),
        FakeSection(start_ms=6000, end_ms=12000, label="B", confidence=0.72),
        FakeSection(start_ms=12000, end_ms=18000, label="A", confidence=0.88),
    ),
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
    with_sections: bool = True,
    with_object: bool = True,
    sections: FakeSectionTimeline = SECTION_LIST,
) -> UUID:
    """Take a song to a succeeded job the way the worker does, and return the job id.

    ``with_sections=False`` is what a job analysed before this artifact existed produces.
    ``with_object=False`` is what the seed leaves behind: a sections row whose object was never
    uploaded, which the route has to answer for rather than fail on.

    The other four artifacts are written too, because a job writes all of them or none - the same
    reason ``test_song_chords.py`` stores this list in its own helper.
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
            timeline=FakeChordTimeline(),
        ),
        sections=artifacts.store_sections(
            store,
            user_id=user_id,
            job_id=running.id,
            timeline=sections,
        ),
    )

    if not with_object:
        key = artifacts.sections_object_key(user_id=user_id, job_id=running.id)
        store.bodies.pop(key, None)
        store.objects.pop(key, None)

    if not with_sections:
        rows = [row for row in rows if row.kind != "sections"]

    finished = queue.complete(conn, job=running, results=rows)
    assert finished is not None
    return finished.id


# --- The list -----------------------------------------------------------------


def test_an_analysed_song_hands_back_its_sections(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The list itself, and not a link to it: this is a screen's read, not a download."""
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
    )

    response = client.get(f"/songs/{song_id}/sections")

    assert response.status_code == 200
    body = response.json()
    assert body["detector"] == "fake-section-detector"
    assert body["vocabulary"] == "1.0"
    assert body["hop_ms"] == 4000
    assert body["sections"] == [
        {"start_ms": 0, "end_ms": 6000, "label": "A", "confidence": 0.91},
        {"start_ms": 6000, "end_ms": 12000, "label": "B", "confidence": 0.72},
        {"start_ms": 12000, "end_ms": 18000, "label": "A", "confidence": 0.88},
    ]

    # Not a presigned link, and nothing that expires - the same as the chord route next door.
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

    row = analysis_result.get_for_job_kind(conn, job_id=job_id, kind="sections")
    assert row is not None

    body = client.get(f"/songs/{song_id}/sections").json()

    assert body["summary"] == row.summary
    # The form is the whole point of the digest: three sections that say A B A, readable from a
    # library row without fetching the list they came from.
    assert body["summary"]["form"] == "A B A"
    assert body["summary"]["sections"] == 3
    assert body["summary"]["confidence"] == 0.837  # the mean of 0.91, 0.72 and 0.88, rounded


# --- Refusals -----------------------------------------------------------------


def test_a_song_that_has_never_been_analysed_is_not_ready(
    client: TestClient,
    store: FakeObjectStore,
    song_id: UUID,
) -> None:
    response = client.get(f"/songs/{song_id}/sections")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert store.bodies == {}


def test_a_job_that_produced_no_sections_is_not_an_error(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A recording with nothing to tell apart is a fact about a recording, not a failure."""
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
        with_sections=False,
    )

    response = client.get(f"/songs/{song_id}/sections")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song's analysis produced no sections."


def test_sections_whose_object_is_gone_are_not_ready(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """The row exists and the bucket does not hold the object - answered, not crashed on."""
    _analyse(
        conn,
        store,
        user_id=user_id,
        song_id=song_id,
        source_key=make_object_key(name="source.wav"),
        with_object=False,
    )

    response = client.get(f"/songs/{song_id}/sections")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_ready"
    assert response.json()["detail"]["message"] == "This song's sections are no longer in storage."


def test_an_unknown_song_is_not_found(client: TestClient, store: FakeObjectStore) -> None:
    response = client.get(f"/songs/{new_id()}/sections")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "song_not_found"
    assert store.bodies == {}


def test_a_request_without_a_token_is_refused(
    store: FakeObjectStore,
    settings_env: None,
) -> None:
    """Reading a section list needs a caller, like every other route."""
    app = create_app()
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as anonymous:
        response = anonymous.get(f"/songs/{UUID(int=0)}/sections")

    assert response.status_code == 401
    assert store.bodies == {}
