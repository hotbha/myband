"""Verifying a Supabase access token, without a network or a database.

The tokens here are built with the same library that verifies them, against settings
pointed at test values. Two families matter: the legacy shared secret (HS256), and
asymmetric keys, where a token is checked against the project's published key set.
The asymmetric cases stop at the boundary where that key set would be fetched - the
interesting line, because it is what decides between accepting a token and admitting
this service is not configured to verify any.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.core import auth
from app.core.config import get_settings
from app.core.problems import ApiProblem, ErrorCode
from cryptography.hazmat.primitives.asymmetric import ec

SECRET = "a-test-secret-long-enough-to-sign-a-token-with"
OTHER_SECRET = "a-different-secret-of-the-same-length"
DATABASE_URL = "postgresql://myband:myband@127.0.0.1:5432/myband"


@pytest.fixture(autouse=True)
def _clean_settings() -> Iterator[None]:
    """Never leave one test's settings cached for the next one."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def shared_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sign with a shared secret, and configure nothing else.

    The empty values are set rather than deleted on purpose: an environment variable
    beats the dotenv file, so setting `SUPABASE_URL=""` is what keeps a developer's
    `apps/api/.env` from deciding which project these tokens came from.
    """
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("SUPABASE_URL", "")
    get_settings.cache_clear()


def _token(
    overrides: dict[str, object] | None = None,
    *,
    drop: tuple[str, ...] = (),
    key: object = SECRET,
    algorithm: str = "HS256",
) -> str:
    """A token shaped the way Supabase issues one."""
    payload: dict[str, object] = {
        "sub": str(uuid4()),
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    payload.update(overrides or {})
    for name in drop:
        payload.pop(name, None)

    return jwt.encode(payload, key, algorithm=algorithm)


def _refused(token: str) -> ApiProblem:
    """Verify a token that must not be accepted, and hand back the refusal."""
    with pytest.raises(ApiProblem) as raised:
        auth.verify_access_token(token)
    return raised.value


# --- The shared secret -------------------------------------------------------


def test_a_valid_token_identifies_its_user(shared_secret: None) -> None:
    user_id = uuid4()

    assert auth.verify_access_token(_token({"sub": str(user_id)})) == user_id


def test_a_token_with_no_subject_is_refused(shared_secret: None) -> None:
    problem = _refused(_token(drop=("sub",)))

    assert problem.status == 401
    assert problem.code is ErrorCode.UNAUTHENTICATED


def test_a_subject_that_is_not_a_user_id_is_refused(shared_secret: None) -> None:
    assert _refused(_token({"sub": "not-a-uuid"})).status == 401


def test_an_expired_token_is_refused(shared_secret: None) -> None:
    expired = _token({"exp": datetime.now(UTC) - timedelta(minutes=5)})

    assert _refused(expired).status == 401


def test_a_token_signed_by_somebody_else_is_refused(shared_secret: None) -> None:
    assert _refused(_token(key=OTHER_SECRET)).status == 401


def test_a_service_role_token_is_not_a_user_token(shared_secret: None) -> None:
    assert _refused(_token({"role": "service_role"})).status == 401


def test_a_token_for_another_audience_is_refused(shared_secret: None) -> None:
    assert _refused(_token({"aud": "something-else"})).status == 401


def test_an_unsigned_token_is_refused(shared_secret: None) -> None:
    """`none` is not on the allowlist, so an unsigned token is never trusted."""
    assert _refused(_token(key="", algorithm="none")).status == 401


def test_a_token_from_another_project_is_refused(
    shared_secret: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://myband.supabase.co")
    get_settings.cache_clear()

    theirs = _token({"iss": "https://someone-else.supabase.co/auth/v1"})
    ours = _token({"iss": "https://myband.supabase.co/auth/v1"})

    assert _refused(theirs).status == 401
    assert auth.verify_access_token(ours)


# --- Misconfiguration --------------------------------------------------------


def test_an_hs256_token_without_a_configured_secret_is_a_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    get_settings.cache_clear()

    problem = _refused(_token())

    assert problem.status == 500
    assert problem.code is ErrorCode.SERVER_MISCONFIGURED


def test_an_asymmetric_token_needs_a_configured_project(shared_secret: None) -> None:
    """No project URL means no key set to check the signature against."""
    token = _token(key=ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")

    problem = _refused(token)

    assert problem.status == 500
    assert problem.code is ErrorCode.SERVER_MISCONFIGURED


def test_a_key_set_that_cannot_be_reached_is_reported_as_unavailable(
    shared_secret: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Port 9 is the discard port: nothing listens, so the fetch fails at once."""
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    get_settings.cache_clear()

    token = _token(key=ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")

    problem = _refused(token)

    assert problem.status == 503
    assert problem.code is ErrorCode.AUTH_UNAVAILABLE


# --- The header --------------------------------------------------------------


@pytest.mark.parametrize("header", [None, "", "Bearer", "Basic abc.def.ghi", "abc.def.ghi"])
def test_an_authorization_header_that_is_not_a_bearer_token_is_refused(
    shared_secret: None,
    header: str | None,
) -> None:
    with pytest.raises(ApiProblem) as raised:
        auth.bearer_token(header)

    assert raised.value.status == 401


def test_the_bearer_scheme_is_matched_case_insensitively(shared_secret: None) -> None:
    assert auth.bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
    assert auth.bearer_token("bearer abc.def.ghi") == "abc.def.ghi"
