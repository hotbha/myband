"""``GET /admin/metrics``: the numbers, and who is allowed to read them.

The endpoint is not part of the product's API, so most of what is asserted here is the
gate - a deployment with no token does not have the route, a deployment with one demands
it - and the rest is that the numbers are read out of ``analysis_jobs`` rather than taken
from the caller.

Needs a migrated database; see ``tests/test_schema.py`` for the environment.
"""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from app.api.routes import metrics as metrics_routes
from app.core.config import get_settings
from app.main import create_app
from app.models import analysis_job
from app.models.analysis_job import AnalysisJob
from app.services import queue
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support import claim_own_job, reuse_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("MYBAND_TEST_DATABASE_URL"),
    reason="set MYBAND_TEST_DATABASE_URL to test against a migrated database",
)

PIPELINE_VERSION = "0.1.0"

# The vocabulary, as locked: the dashboard and the API both speak this and nothing else.
STATUSES = ("queued", "dispatched", "running", "succeeded", "failed", "canceled")

# Where the request appears to come from. The gate reads the socket address, so a test
# has to be able to say "this one came from elsewhere".
LOCAL = "127.0.0.1"
REMOTE = "203.0.113.7"

TOKEN = "operator-token"

# A production boot insists on every third-party credential (Settings), so the cases that
# need MYBAND_ENV=production supply stand-ins for all of them.
PRODUCTION_SECRETS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "R2_ACCOUNT_ID": "account-id",
    "R2_ACCESS_KEY_ID": "access-key-id",
    "R2_SECRET_ACCESS_KEY": "secret-access-key",
    "RUNPOD_API_KEY": "runpod-api-key",
    "RUNPOD_ENDPOINT_ID": "runpod-endpoint-id",
}


@pytest.fixture
def metrics_app(
    monkeypatch: pytest.MonkeyPatch,
    settings_env: None,
    conn: psycopg.Connection,
) -> Iterator[Callable[..., FastAPI]]:
    """Build the app on the test's transaction, with the environment this case wants.

    The gate reads its settings while a request is being handled, so the environment has
    to be in place and the settings cache cleared *before* the app is built - which is why
    this returns a factory rather than one ready-made app.
    """

    def _build(*, env: str = "development", token: str | None = None) -> FastAPI:
        monkeypatch.setenv("MYBAND_ENV", env)
        if token is None:
            monkeypatch.delenv("MYBAND_METRICS_TOKEN", raising=False)
        else:
            monkeypatch.setenv("MYBAND_METRICS_TOKEN", token)
        if env == "production":
            for name, value in PRODUCTION_SECRETS.items():
                monkeypatch.setenv(name, value)

        get_settings.cache_clear()
        app = create_app()
        # The route still believes it owns the transaction; the `conn` fixture rolls it
        # back, so nothing the request wrote outlives the test.
        monkeypatch.setattr(metrics_routes, "connect", lambda **_: reuse_connection(conn))
        return app

    yield _build


def _call(
    app: FastAPI,
    *,
    host: str = LOCAL,
    authorization: str | bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    """One GET, from the address and with the header this case is about."""
    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(app, client=(host, 50000)) as client:
        response = client.get("/admin/metrics", headers=headers)
    return response.status_code, response.json()


def _running_job(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    minutes_silent: int,
) -> AnalysisJob:
    """A running job whose worker has (or has not) gone quiet."""
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=make_object_key(name="metrics.wav"),
    )
    assert outcome.job is not None

    running = queue.begin(conn, job=claim_own_job(conn, song_id=song_id))
    assert running is not None

    if minutes_silent:
        conn.execute(
            "update public.analysis_jobs set heartbeat_at = %s where id = %s",
            (datetime.now(UTC) - timedelta(minutes=minutes_silent), running.id),
        )

    return running


# --- The gate -----------------------------------------------------------------


def test_a_deployment_without_a_token_does_not_publish_the_endpoint(metrics_app) -> None:
    """Production with no MYBAND_METRICS_TOKEN: the caller is told there is no such route.

    Not a 401: there is nothing to authenticate against, and a deployment that was never
    given a token should not advertise that it has an operator endpoint at all.
    """
    status, body = _call(metrics_app(env="production"))

    assert status == 404
    assert body["detail"]["code"] == "invalid_request"


def test_staging_without_a_token_is_not_published_either(metrics_app) -> None:
    """Only a development run gets the convenience; anything deployed sets the token."""
    status, _ = _call(metrics_app(env="staging"))

    assert status == 404


def test_a_local_development_run_may_read_its_own_queue(metrics_app) -> None:
    status, body = _call(metrics_app())

    assert status == 200
    assert set(body["jobs"]["by_status"]) == set(STATUSES)


def test_a_remote_caller_is_refused_even_in_development(metrics_app) -> None:
    """A developer's shortcut must not become a deployed environment's hole."""
    status, _ = _call(metrics_app(), host=REMOTE)

    assert status == 404


def test_the_token_lets_the_operator_in_from_anywhere(metrics_app) -> None:
    status, body = _call(metrics_app(token=TOKEN), host=REMOTE, authorization=f"Bearer {TOKEN}")

    assert status == 200
    assert body["library"]["songs"] >= 0


def test_a_missing_or_wrong_token_is_unauthorised(metrics_app) -> None:
    """With a token configured the endpoint is real, so refusing is 401, not a 404."""
    app = metrics_app(token=TOKEN)

    assert _call(app, host=REMOTE)[0] == 401
    assert _call(app, host=REMOTE, authorization="Bearer nope")[0] == 401
    # A raw token without the scheme is not a credential.
    assert _call(app, host=REMOTE, authorization=TOKEN)[0] == 401

    status, body = _call(app, host=REMOTE, authorization="Bearer nope")
    assert status == 401
    assert body["detail"]["code"] == "unauthenticated"


def test_a_token_that_is_not_ascii_is_refused_rather_than_crashing(metrics_app) -> None:
    """``compare_digest`` refuses non-ASCII strings; a header is the caller's to set.

    Sent as latin-1 bytes because that is what an HTTP header can actually carry - the
    value has to survive the transport and still be a string that cannot match.
    """
    status, _ = _call(
        metrics_app(token=TOKEN),
        host=REMOTE,
        authorization="Bearer tökén".encode("latin-1"),
    )

    assert status == 401


# --- The numbers --------------------------------------------------------------


def test_every_status_the_schema_allows_is_reported(metrics_app) -> None:
    """All six, so a status added later cannot quietly disappear from the dashboard."""
    _, body = _call(metrics_app())

    counts = body["jobs"]["by_status"]
    assert set(counts) == set(STATUSES)
    assert all(isinstance(value, int) for value in counts.values())
    assert body["window_seconds"] == 3600
    assert body["jobs"]["in_flight"] == counts["dispatched"] + counts["running"]


def test_the_numbers_follow_the_queue(
    metrics_app,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """Queue a job and start it, and watch the depth move one state at a time.

    Asserted as deltas rather than absolutes - the counts are for the whole table, and this
    suite shares its database with the seed - and ``own_queue`` empties the active set
    first so the delta is this job's and nothing else's.
    """
    app = metrics_app()

    before = _call(app)[1]

    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version=PIPELINE_VERSION,
        source_object_key=make_object_key(name="metrics.wav"),
    )
    assert outcome.job is not None
    queued = _call(app)[1]

    started = queue.begin(conn, job=claim_own_job(conn, song_id=song_id))
    assert started is not None
    running = _call(app)[1]

    assert queued["jobs"]["by_status"]["queued"] == before["jobs"]["by_status"]["queued"] + 1
    assert queued["jobs"]["oldest_queued_seconds"] is not None
    assert running["jobs"]["by_status"]["queued"] == before["jobs"]["by_status"]["queued"]
    assert running["jobs"]["by_status"]["running"] == before["jobs"]["by_status"]["running"] + 1
    assert running["jobs"]["in_flight"] == before["jobs"]["in_flight"] + 1
    assert running["jobs"]["oldest_in_flight_seconds"] is not None
    assert running["library"]["songs"] >= 1
    assert running["library"]["song_owners"] >= 1


def test_a_reaped_worker_is_counted_separately_from_an_ordinary_failure(
    metrics_app,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    own_queue: None,
) -> None:
    """``reaped_recently`` is the sweep's fingerprint, and the two are different news.

    ``own_queue`` is what makes the delta this job's: the sweep is global by design, and the
    seed leaves a job in flight, so without it a sweep would reap that one too.
    """
    app = metrics_app()
    before = _call(app)[1]

    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        make_object_key=make_object_key,
        minutes_silent=60,
    )
    reaped = queue.reap_stale(conn, older_than=timedelta(minutes=15))
    assert job.id in {reaped_job.id for reaped_job in reaped}

    after = _call(app)[1]

    assert after["jobs"]["by_status"]["failed"] == before["jobs"]["by_status"]["failed"] + 1
    assert after["jobs"]["failed_recently"] == before["jobs"]["failed_recently"] + 1
    assert after["jobs"]["reaped_recently"] == before["jobs"]["reaped_recently"] + 1


def test_a_failure_the_worker_reported_is_not_counted_as_a_reap(
    metrics_app,
    conn: psycopg.Connection,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
) -> None:
    """A decode error is the product working; only silence is the sweep's business."""
    app = metrics_app()
    before = _call(app)[1]

    job = _running_job(
        conn,
        user_id=user_id,
        song_id=song_id,
        make_object_key=make_object_key,
        minutes_silent=0,
    )
    assert queue.fail(conn, job=job, error_code="decode_error") is not None

    after = _call(app)[1]

    assert after["jobs"]["failed_recently"] == before["jobs"]["failed_recently"] + 1
    assert after["jobs"]["reaped_recently"] == before["jobs"]["reaped_recently"]


def test_a_zero_window_counts_nothing_as_recent(conn: psycopg.Connection) -> None:
    """The window is a parameter, so "recently" is testable without touching a clock."""
    stats = analysis_job.queue_stats(conn, window=timedelta(0))

    assert stats.window == timedelta(0)
    assert stats.finished_recently == 0
    assert stats.failed_recently == 0
    assert stats.reaped_recently == 0
    assert stats.in_flight == stats.dispatched + stats.running
    assert stats.observed_at is not None
