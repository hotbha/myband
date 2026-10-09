"""Operator metrics.

One endpoint, ``GET /admin/metrics``, for whoever is running the platform rather than
for the browser: queue depth, the age of the oldest job in each in-flight state, and how
much finished recently. It reports counts and ages, never a user's data.

It authenticates differently from the product's routes because it is not part of the
product: a shared token from the environment, not a Supabase session. A deployment that
does not set ``MYBAND_METRICS_TOKEN`` does not publish the endpoint at all - it answers
404 - and a local development run may read it over loopback without one.
"""

import secrets
from http import HTTPStatus
from typing import Annotated

from app.core.config import Settings, get_settings
from app.core.db import connect
from app.core.problems import ApiProblem, ErrorCode
from app.models import analysis_job
from app.models import song as song_model
from app.schemas.metrics import JobActivityOut, JobCountsOut, LibraryOut, MetricsOut
from fastapi import APIRouter, Depends, Header, Request

router = APIRouter(tags=["ops"])

# Where a local run's own traffic comes from. A browser on the same machine arrives as
# 127.0.0.1; "localhost" is here for a client that resolves it without connecting over
# the loopback address itself.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback(request: Request) -> bool:
    """Whether the request arrived over the loopback interface.

    Read from the socket, never from a forwarded-for header: a header is the caller's to
    set, and this decides whether a token is needed at all.
    """
    client = request.client
    return client is not None and client.host in LOOPBACK_HOSTS


def _matches(presented: str, expected: str) -> bool:
    """Constant-time comparison that answers ``False`` instead of raising.

    ``compare_digest`` refuses non-ASCII strings, and the presented value comes straight
    out of a request header, so a token typed with an accent has to be a refusal rather
    than a 500.
    """
    try:
        return secrets.compare_digest(presented, expected)
    except TypeError:
        return False


def _presented_token(authorization: str | None) -> str | None:
    """The bearer token in the header, or ``None`` when there is not one.

    Not ``core.auth.bearer_token``: that one raises "Sign in to continue.", which is a
    sentence for a user who lost their session, and this header carries an operator's
    shared token instead.
    """
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None

    return token.strip() or None


def require_metrics_access(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Let the operator in, or answer as if this route did not exist.

    Three cases, and the asymmetry between them is the point:

    * **A token is configured.** The caller presents it as ``Authorization: Bearer
      <token>``. Anything else is a 401: this deployment publishes the endpoint, and the
      caller is not carrying the secret.
    * **No token, and this is a development run reached over loopback.** Allowed, so a
      developer can read their own queue without ceremony.
    * **No token anywhere else** - staging, production, or a caller that is not on this
      machine - is a 404. A deployment that was never given a token does not have this
      endpoint, and says so, rather than advertising one it will not answer. The check is
      on the socket address rather than on a header, so a proxy on the same host cannot
      turn a remote request into a local one.
    """
    expected = settings.metrics_token.get_secret_value()
    if not expected:
        if settings.env == "development" and _is_loopback(request):
            return
        raise ApiProblem(
            HTTPStatus.NOT_FOUND,
            ErrorCode.INVALID_REQUEST,
            "No such endpoint.",
        )

    presented = _presented_token(authorization)
    if presented is None or not _matches(presented, expected):
        raise ApiProblem(
            HTTPStatus.UNAUTHORIZED,
            ErrorCode.UNAUTHENTICATED,
            "A metrics token is required.",
        )


@router.get("/admin/metrics", dependencies=[Depends(require_metrics_access)])
def metrics() -> MetricsOut:
    """The platform's queue and library, as counts and ages."""
    with connect() as conn:
        stats = analysis_job.queue_stats(conn)
        library = song_model.library_stats(conn)

    return MetricsOut(
        generated_at=stats.observed_at,
        window_seconds=int(stats.window.total_seconds()),
        jobs=JobActivityOut(
            by_status=JobCountsOut(
                queued=stats.queued,
                dispatched=stats.dispatched,
                running=stats.running,
                succeeded=stats.succeeded,
                failed=stats.failed,
                canceled=stats.canceled,
            ),
            in_flight=stats.in_flight,
            oldest_queued_seconds=stats.oldest_queued_seconds,
            oldest_in_flight_seconds=stats.oldest_in_flight_seconds,
            finished_recently=stats.finished_recently,
            failed_recently=stats.failed_recently,
            reaped_recently=stats.reaped_recently,
        ),
        library=LibraryOut(songs=library.songs, song_owners=library.song_owners),
    )
