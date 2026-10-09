"""Access-token verification for the browser-facing routes.

Every route that reads or writes a user's data starts by proving who is calling.
The browser sends a Supabase access token as ``Authorization: Bearer ...`` and it
is verified here, in process:

* A project on asymmetric signing keys - the default, and what ``supabase start``
  issues locally - publishes a JWKS, so tokens are verified against it with no
  round trip to the Auth server per request. ``PyJWKClient`` caches the key set.
* A project still on the legacy shared secret signs HS256, verified with
  ``SUPABASE_JWT_SECRET``.

The algorithm is read from the token's header but never chooses which key is
trusted: HS* is verified with our own secret, everything else with a key from the
project's JWKS. That is what makes the classic algorithm-confusion attack -
re-sign a token with HS256 using the public key as the HMAC secret - fail here.

A verified token yields exactly one thing: the user id. Nothing else in it is
trusted, and every query the API runs is still scoped by that id, because the API
connects as ``postgres`` and therefore bypasses RLS (docs/schema.md).
"""

from functools import lru_cache
from http import HTTPStatus
from uuid import UUID

import jwt
from app.core.config import Settings, get_settings
from app.core.problems import ApiProblem, ErrorCode
from jwt import PyJWKClient

# What Supabase stamps on a signed-in user's token. A service-role token carries
# no `sub`, so the subject check below rejects it as well.
AUDIENCE = "authenticated"
USER_ROLE = "authenticated"

# The algorithms this service verifies. `none` is not one of them.
ALLOWED_ALGORITHMS = frozenset(
    {"HS256", "HS384", "HS512", "ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "EdDSA"}
)
SYMMETRIC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})

# Clock skew tolerated between this server and the Auth server.
LEEWAY_SECONDS = 30

# How long to wait on the JWKS endpoint before treating it as unavailable.
JWKS_TIMEOUT_SECONDS = 10


def verify_access_token(token: str) -> UUID:
    """Return the user id a Supabase access token vouches for.

    Raises :class:`ApiProblem`: 401 for anything wrong with the token, 503 when
    the JWKS endpoint cannot be reached, 500 when this service is not configured
    to verify tokens at all.
    """
    settings = get_settings()
    return _subject_of(_decode(token, settings, _algorithm_of(token)))


def bearer_token(authorization: str | None) -> str:
    """Pull the token out of an ``Authorization`` header.

    The scheme is matched case-insensitively because HTTP header *values* may be
    sent in any case; the token itself is opaque.
    """
    if not authorization:
        raise _invalid("Sign in to continue.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _invalid("Authorization must be 'Bearer <access token>'.")

    return token.strip()


def _algorithm_of(token: str) -> str:
    """The token's own ``alg``, checked against the allowlist before it is used."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as error:
        raise _invalid("The access token could not be read. Sign in again.") from error

    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in ALLOWED_ALGORITHMS:
        raise _invalid("The access token uses an unsupported signature algorithm.")

    return algorithm


def _decode(token: str, settings: Settings, algorithm: str) -> dict[str, object]:
    """Verify the signature, expiry, audience, issuer and required claims."""
    try:
        return jwt.decode(
            token,
            _verification_key(token, settings, algorithm),
            algorithms=[algorithm],
            audience=AUDIENCE,
            issuer=_issuer(settings),
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as error:
        raise _invalid("The access token is invalid or has expired. Sign in again.") from error


def _verification_key(token: str, settings: Settings, algorithm: str) -> object:
    """The key this token must be signed with, chosen by algorithm family."""
    if algorithm in SYMMETRIC_ALGORITHMS:
        secret = settings.supabase_jwt_secret.get_secret_value()
        if not secret:
            raise _misconfigured("SUPABASE_JWT_SECRET is required to verify HS256 access tokens.")
        return secret

    try:
        return _jwks_client(_jwks_url(settings)).get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as error:
        raise ApiProblem(
            HTTPStatus.SERVICE_UNAVAILABLE,
            ErrorCode.AUTH_UNAVAILABLE,
            "Sign-in verification is temporarily unavailable. Please try again.",
        ) from error
    except jwt.PyJWKClientError as error:
        raise _invalid("The access token was not signed by this project.") from error


def _jwks_url(settings: Settings) -> str:
    if not settings.supabase_url:
        raise _misconfigured("SUPABASE_URL is required to verify asymmetric access tokens.")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _issuer(settings: Settings) -> str | None:
    """The ``iss`` claim Supabase stamps, or ``None`` to skip that check."""
    if not settings.supabase_url:
        return None
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    """One client per JWKS URL, reused so the key set stays cached in memory."""
    return PyJWKClient(url, cache_keys=True, timeout=JWKS_TIMEOUT_SECONDS)


def _subject_of(claims: dict[str, object]) -> UUID:
    if claims.get("role") != USER_ROLE:
        raise _invalid("This token is not a signed-in user's token.")

    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise _invalid("The access token does not identify a user.")

    try:
        return UUID(subject)
    except ValueError as error:
        raise _invalid("The access token's subject is not a user id.") from error


def _invalid(message: str) -> ApiProblem:
    return ApiProblem(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHENTICATED, message)


def _misconfigured(message: str) -> ApiProblem:
    return ApiProblem(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.SERVER_MISCONFIGURED, message)
