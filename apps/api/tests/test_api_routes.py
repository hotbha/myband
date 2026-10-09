"""The HTTP surface, walked the way the browser walks it.

These tests drive the real application - real routes, real services, real SQL - with
three things swapped: the database connection (for the rolled-back one the ``conn``
fixture provides), the object store (for ``FakeObjectStore``), and the caller's
identity (for a user the test created).

That is enough to sign in as somebody, presign an upload, "PUT" the bytes, complete
it and read the song and the job back - the whole success criterion, minus a browser
and a bucket.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable, Iterator
from uuid import UUID

import psycopg
import pytest
from app.api.deps import current_user_id
from app.api.routes import jobs as jobs_routes
from app.api.routes import songs as songs_routes
from app.api.routes import uploads as uploads_routes
from app.main import create_app
from app.services.storage import get_object_store
from fastapi.testclient import TestClient
from tests.fakes import FakeObjectStore
from tests.support import reuse_connection, start

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

MAX_BYTES = 200 * 1024 * 1024


@pytest.fixture
def store() -> FakeObjectStore:
    """An object store that remembers what it was asked for."""
    return FakeObjectStore()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    settings_env: None,
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
) -> Iterator[TestClient]:
    """The API, on the test's transaction, signed in as ``user_id``."""
    for module in (uploads_routes, songs_routes, jobs_routes):
        monkeypatch.setattr(module, "connect", lambda **_: reuse_connection(conn))

    app = create_app()
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as test_client:
        yield test_client


def _presign(client: TestClient, **body: object) -> dict[str, object]:
    """Presign through the API, with the request body a browser would send."""
    response = client.post(
        "/uploads/presign",
        json={"filename": "track.mp3", "content_type": "audio/mpeg", "bytes": 4096} | body,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- The whole flow ----------------------------------------------------------


def test_a_user_can_upload_an_mp3_and_get_a_queued_job(
    client: TestClient,
    store: FakeObjectStore,
) -> None:
    """Presign, PUT, complete, then read the job back - all over HTTP."""
    presigned = _presign(client)
    upload = presigned["upload"]
    object_key = upload["object_key"]

    assert upload["status"] == "pending"
    assert presigned["method"] == "PUT"
    assert presigned["headers"] == {"Content-Type": "audio/mpeg"}
    assert presigned["max_bytes"] == MAX_BYTES
    assert presigned["upload_url"].startswith(f"https://bucket.test/{object_key}?")

    # The browser PUTs the file. This is the one step that never reaches the API.
    store.put(object_key, body_bytes=4096)

    completed = client.post(
        "/uploads/complete",
        json={"upload_id": upload["id"], "title": "Midnight Drive"},
    )

    assert completed.status_code == 201, completed.text
    result = completed.json()
    assert result["upload"]["status"] == "completed"
    assert result["upload"]["bytes_actual"] == 4096
    assert result["song"]["title"] == "Midnight Drive"
    assert result["song"]["source_object_key"] == object_key
    assert result["job"]["status"] == "queued"

    song_id, job_id = result["song"]["id"], result["job"]["id"]

    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"
    assert client.get(f"/uploads/{upload['id']}").json()["song_id"] == song_id

    song = client.get(f"/songs/{song_id}").json()
    assert song["id"] == song_id
    assert song["job"]["id"] == job_id

    library = client.get("/songs").json()["songs"]
    assert [item["id"] for item in library] == [song_id]
    assert library[0]["job"]["status"] == "queued"


def test_completing_the_same_upload_twice_answers_200_and_the_same_song(
    client: TestClient,
    store: FakeObjectStore,
) -> None:
    presigned = _presign(client)
    store.put(presigned["upload"]["object_key"], body_bytes=4096)
    body = {"upload_id": presigned["upload"]["id"]}

    first = client.post("/uploads/complete", json=body)
    second = client.post("/uploads/complete", json=body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["song"]["id"] == first.json()["song"]["id"]
    assert second.json()["job"]["id"] == first.json()["job"]["id"]


# --- Refusals ----------------------------------------------------------------


def test_a_request_without_a_token_is_refused(store: FakeObjectStore, settings_env: None) -> None:
    """No override for the caller here: this is the unauthenticated path."""
    app = create_app()
    app.dependency_overrides[get_object_store] = lambda: store

    with TestClient(app) as anonymous:
        response = anonymous.get("/songs")

    assert response.status_code == 401
    assert response.json() == {
        "detail": {"code": "unauthenticated", "message": "Sign in to continue."}
    }


def test_a_file_type_the_product_does_not_take_is_refused_before_any_row_exists(
    client: TestClient,
    conn: psycopg.Connection,
    user_id: UUID,
) -> None:
    response = client.post(
        "/uploads/presign",
        json={"filename": "track.flac", "content_type": "audio/flac"},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_media_type"
    assert (
        conn.execute(
            "select count(*) as n from public.uploads where user_id = %s", (user_id,)
        ).fetchone()["n"]
        == 0
    )


def test_an_upload_that_belongs_to_somebody_else_is_not_found(
    client: TestClient,
    store: FakeObjectStore,
    conn: psycopg.Connection,
    make_user: Callable[..., UUID],
) -> None:
    theirs = start(conn, store, make_user())

    response = client.post("/uploads/complete", json={"upload_id": str(theirs.upload.id)})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "upload_not_found"


def test_a_body_that_is_not_valid_leaves_in_the_same_shape(client: TestClient) -> None:
    """Pydantic's own 422 is normalized, so a client parses one shape either way."""
    response = client.post("/uploads/presign", json={"filename": "", "bytes": 0})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert "filename" in detail["message"]


def test_a_library_page_cannot_ask_for_more_than_the_cap(client: TestClient) -> None:
    assert client.get("/songs", params={"limit": 0}).status_code == 422
    assert client.get("/songs", params={"limit": 101}).status_code == 422
    assert client.get("/songs", params={"limit": 1}).status_code == 200


# --- Plumbing ----------------------------------------------------------------


def test_health_answers_without_a_token(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_the_web_origin_may_call_this_api_from_a_browser(client: TestClient) -> None:
    preflight = client.options(
        "/uploads/presign",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
