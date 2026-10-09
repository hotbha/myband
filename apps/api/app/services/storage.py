"""Cloudflare R2 access - the only place this service talks to S3.

R2 speaks the S3 API, so ``boto3`` is the whole client. Four capabilities are used:
signing a PUT URL that lets a browser fill one object without credentials, a HEAD
afterwards to find out what actually landed, a GET of a recording for the analysis
worker, and a PUT of the artifacts the worker produced. The first two are the API's
and the last two are the worker's - a browser never holds a credential, and the API
process never holds audio, which is what keeps "FastAPI never receives file bytes"
true.

``R2_ENDPOINT_URL`` overrides the endpoint, which is how a local run points at
MinIO; everything else about the client is identical, because MinIO is S3 too.

Errors are translated rather than leaked: boto3 raises ``ClientError`` carrying the
bucket's XML, which is neither safe nor useful to render in a UI. A missing object
is ``None`` - the expected answer to "did the PUT happen", not an exception - and
anything else becomes a 503 the caller can retry.
"""

from dataclasses import dataclass
from functools import lru_cache
from http import HTTPStatus
from typing import Any, Protocol

import boto3
from app.core.config import Settings, get_settings
from app.core.problems import ApiProblem, ErrorCode
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

# R2 wants a region for SigV4 and accepts this placeholder for "any".
R2_REGION = "auto"

# A HEAD that hangs must not hold a request open indefinitely.
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10

# A bucket that is not listable answers 403 for a key it does not have.
MISSING_STATUSES = frozenset({403, 404})

# Content types that say nothing about a file; stored as NULL instead.
GENERIC_CONTENT_TYPES = frozenset({"binary/octet-stream", "application/octet-stream"})


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """What the bucket reports about an object it holds."""

    bytes: int
    content_type: str | None
    etag: str | None


class ObjectStore(Protocol):
    """The storage seam, so the upload lifecycle is testable without a bucket."""

    def presign_put(self, *, object_key: str, content_type: str, expires_in: int) -> str:
        """A URL the browser can PUT this one object to, and nothing else."""
        ...

    def head(self, *, object_key: str) -> ObjectInfo | None:
        """What the bucket holds at ``object_key``, or ``None`` when nothing does."""
        ...

    def download(self, *, object_key: str) -> bytes | None:
        """The object's bytes, or ``None`` when the bucket does not hold it.

        The analysis worker's read: the audio it analyses was uploaded straight
        from a browser to the bucket, so this is how it reaches the pipeline
        without the API ever having held it.
        """
        ...

    def put_bytes(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
    ) -> ObjectInfo:
        """Write an object this process produced, and report what landed.

        The analysis worker's write (the MIDI it transcribed). Callers always know
        the content type of their own artifact, so unlike a browser's upload there
        is nothing to reconcile afterwards.
        """
        ...


class R2ObjectStore:
    """An :class:`ObjectStore` backed by Cloudflare R2, or anything S3-shaped."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        """Build the S3 client for ``settings``, or use the one handed in.

        ``client`` is the test seam: it lets a stub answer in the place of boto3 so
        that what this adapter does with a bucket's answers can be checked without a
        bucket.
        """
        self._settings = settings
        self._bucket = settings.r2_bucket
        self._client = client if client is not None else _build_client(settings)

    def presign_put(self, *, object_key: str, content_type: str, expires_in: int) -> str:
        """Sign a PUT for exactly one key.

        ``Content-Type`` is signed, so the browser has to send that exact value and
        R2 - not the API - is what holds it to it. The type stored with the object
        is therefore the one this service accepted.
        """
        self._require_configuration()
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def head(self, *, object_key: str) -> ObjectInfo | None:
        """Report the object's size, content type and ETag."""
        self._require_configuration()
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as error:
            if _status_of(error) in MISSING_STATUSES:
                return None
            raise _problem_for(error) from error
        except BotoCoreError as error:
            raise _unavailable() from error

        return ObjectInfo(
            bytes=int(response.get("ContentLength") or 0),
            content_type=_clean_content_type(response.get("ContentType")),
            etag=_clean_etag(response.get("ETag")),
        )

    def download(self, *, object_key: str) -> bytes | None:
        """Read an object whole, or ``None`` when the bucket does not hold it.

        Whole, rather than streamed: the analysis worker needs every byte of the
        recording before it can say anything about it, and the size ceiling is
        already `upload_rules.MAX_UPLOAD_BYTES`. A missing object is ``None`` and
        not an error - "the source is gone" is a job failure with a name, not a
        broken call - while a refusal and an outage are two different problems, and
        only one of them is worth another go.
        """
        self._require_configuration()
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        except ClientError as error:
            if _status_of(error) in MISSING_STATUSES:
                return None
            raise _problem_for(error) from error
        except BotoCoreError as error:
            raise _unavailable() from error

        return response["Body"].read()

    def put_bytes(self, *, object_key: str, body: bytes, content_type: str) -> ObjectInfo:
        """Write an artifact, and report the same shape a HEAD would.

        The caller measures nothing: the object's size is ``len(body)``, the type is
        the one it declared, and the ETag comes back from the bucket. Writing the
        same key twice overwrites it, which is what makes a re-run of a pipeline
        idempotent rather than a source of duplicates.

        A refusal is translated like any other, and this is the call where it matters:
        a bucket whose policy does not allow this content type answers 415, and that is
        a ``storage_rejected`` - a policy to fix, not a call to retry.
        """
        self._require_configuration()
        try:
            response = self._client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=body,
                ContentType=content_type,
            )
        except ClientError as error:
            raise _problem_for(error) from error
        except BotoCoreError as error:
            raise _unavailable() from error

        return ObjectInfo(
            bytes=len(body),
            content_type=content_type,
            etag=_clean_etag(response.get("ETag")),
        )

    def _require_configuration(self) -> None:
        """Fail with a readable message instead of botocore's credential error."""
        settings = self._settings
        missing = [
            name
            for name, value in (
                (
                    "R2_ENDPOINT_URL or R2_ACCOUNT_ID",
                    settings.r2_endpoint_url or settings.r2_account_id,
                ),
                ("R2_ACCESS_KEY_ID", settings.r2_access_key_id.get_secret_value()),
                ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise ApiProblem(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                ErrorCode.SERVER_MISCONFIGURED,
                "Object storage is not configured: " + ", ".join(missing),
            )


def get_object_store() -> ObjectStore:
    """The process-wide store, built once from settings."""
    return _store()


@lru_cache(maxsize=1)
def _store() -> ObjectStore:
    return R2ObjectStore(get_settings())


def _endpoint_url(settings: Settings) -> str | None:
    """Where the S3 API lives: the explicit override, else Cloudflare's per-account host."""
    if settings.r2_endpoint_url:
        return settings.r2_endpoint_url.rstrip("/")
    if settings.r2_account_id:
        return f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return None


def _build_client(settings: Settings) -> Any:
    """The boto3 client: SigV4-signed, time-bounded, retried twice.

    Failures are surfaced to the caller for translation rather than raised from
    botocore's own exception hierarchy.
    """
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(settings),
        aws_access_key_id=settings.r2_access_key_id.get_secret_value() or None,
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value() or None,
        region_name=settings.r2_region,
        config=Config(
            signature_version="s3v4",
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            read_timeout=READ_TIMEOUT_SECONDS,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def _status_of(error: ClientError) -> int:
    """The HTTP status the bucket answered with, or 0 when it is not reported."""
    metadata = error.response.get("ResponseMetadata") or {}
    try:
        return int(metadata.get("HTTPStatusCode") or 0)
    except (TypeError, ValueError):
        return 0


def _problem_for(error: ClientError) -> ApiProblem:
    """The problem a bucket's refusal translates to.

    A 4xx that is not "missing" is the bucket refusing the request itself: a content type
    its policy does not allow, a key it will not accept. Waiting cannot change that, so it
    gets its own code rather than the 503 that means "try again" - the two lead whoever is
    on call to different places.
    """
    status = _status_of(error)
    if 400 <= status < 500:
        return ApiProblem(
            HTTPStatus.BAD_GATEWAY,
            ErrorCode.STORAGE_REJECTED,
            "Object storage refused the request: its policy does not allow it.",
        )
    return _unavailable()


def _unavailable() -> ApiProblem:
    return ApiProblem(
        HTTPStatus.SERVICE_UNAVAILABLE,
        ErrorCode.STORAGE_UNAVAILABLE,
        "Object storage is temporarily unavailable. Please try again.",
    )


def _clean_content_type(value: object) -> str | None:
    """The object's content type, or ``None`` when it is absent or generic.

    ``uploads.content_type_actual`` requires 3 to 128 characters, so an empty or
    placeholder value is stored as NULL rather than smuggled through as an empty
    string.
    """
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not 3 <= len(cleaned) <= 128 or cleaned in GENERIC_CONTENT_TYPES:
        return None

    return cleaned


def _clean_etag(value: object) -> str | None:
    """S3 quotes its ETag; ``uploads.etag_actual`` holds the bare value."""
    if not isinstance(value, str):
        return None

    cleaned = value.strip().strip('"')[:128]
    return cleaned or None
