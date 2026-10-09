"""The R2 adapter: what it does with the bucket's answers.

A stub stands in for boto3, so the translation this module exists to do - a missing
object is ``None``, a quoted ETag becomes a bare one, a generic content type becomes
``None``, a provider error becomes a 503, and a store that was never configured never
reaches the network at all - is checked without a bucket and without credentials.
Signing a URL is boto3's business; what it is *asked* for is this module's.
"""

from typing import Any

import pytest
from app.core.config import Settings
from app.core.problems import ApiProblem, ErrorCode
from app.services.storage import ObjectInfo, R2ObjectStore
from botocore.exceptions import ClientError

BUCKET = "myband-audio"
ENDPOINT_OVERRIDE = "http://127.0.0.1:54321/storage/v1/s3"
OBJECT_KEY = "users/018f2f3a-1111-7000-8000-000000000001/uploads/track.mp3"
# The shape a MIDI artifact has: `workers.artifacts.midi_object_key`.
MIDI_KEY = (
    "users/018f2f3a-1111-7000-8000-000000000001"
    "/analysis/018f2f3a-2222-7000-8000-000000000002/transcription.mid"
)


class StubS3:
    """A boto3 client that answers with whatever a test handed it."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response or {}

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append({"operation": operation, **kwargs})
        return f"https://bucket.test/signed?op={operation}"


def _settings(**overrides: str) -> Settings:
    """Settings with storage configured, read from nothing else.

    ``_env_file=None`` matters: without it, a developer's ``apps/api/.env`` would
    supply a real endpoint and credentials, and these assertions would be about their
    laptop instead of about this module.
    """
    return Settings(
        _env_file=None,
        **{
            "DATABASE_URL": "postgresql://myband:myband@127.0.0.1:5432/myband",
            "R2_ACCOUNT_ID": "test-account",
            "R2_ACCESS_KEY_ID": "an-access-key",
            "R2_SECRET_ACCESS_KEY": "a-secret-key",
            "R2_BUCKET": BUCKET,
            **overrides,
        },
    )


def _client_error(status: int) -> ClientError:
    """The error shape botocore raises for a bucket's HTTP answer."""
    return ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "no"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "HeadObject",
    )


def _refused(call: Any) -> ApiProblem:
    with pytest.raises(ApiProblem) as raised:
        call()
    return raised.value


# --- Head --------------------------------------------------------------------


def test_an_object_that_is_not_there_is_not_an_error() -> None:
    """``None`` is the answer to "did the PUT happen", so it is not exceptional."""
    store = R2ObjectStore(_settings(), client=StubS3(error=_client_error(404)))

    assert store.head(object_key=OBJECT_KEY) is None


def test_a_forbidden_lookup_also_reads_as_missing() -> None:
    """A bucket that may not be listed answers 403 for a key it does not hold."""
    store = R2ObjectStore(_settings(), client=StubS3(error=_client_error(403)))

    assert store.head(object_key=OBJECT_KEY) is None


def test_anything_else_the_bucket_says_becomes_a_503() -> None:
    store = R2ObjectStore(_settings(), client=StubS3(error=_client_error(500)))

    problem = _refused(lambda: store.head(object_key=OBJECT_KEY))

    assert problem.status == 503
    assert problem.code is ErrorCode.STORAGE_UNAVAILABLE


def test_head_reports_the_size_the_type_and_a_bare_etag() -> None:
    client = StubS3(
        {
            "ContentLength": 4096,
            "ContentType": "audio/mpeg",
            "ETag": '"5d41402abc4b2a76b9719d911017c592"',
        }
    )

    info = R2ObjectStore(_settings(), client=client).head(object_key=OBJECT_KEY)

    assert info == ObjectInfo(
        bytes=4096,
        content_type="audio/mpeg",
        etag="5d41402abc4b2a76b9719d911017c592",
    )
    assert client.calls == [{"Bucket": BUCKET, "Key": OBJECT_KEY}]


def test_a_generic_content_type_is_stored_as_nothing() -> None:
    """`uploads.content_type_actual` may not hold a placeholder, and may not be empty."""
    client = StubS3({"ContentLength": 10, "ContentType": "application/octet-stream"})

    info = R2ObjectStore(_settings(), client=client).head(object_key=OBJECT_KEY)

    assert info is not None
    assert info.content_type is None


def test_a_size_the_bucket_omits_reads_as_zero() -> None:
    client = StubS3({"ContentType": "audio/mpeg"})

    info = R2ObjectStore(_settings(), client=client).head(object_key=OBJECT_KEY)

    assert info is not None
    assert info.bytes == 0


# --- Presign -----------------------------------------------------------------


def test_presigning_signs_one_key_with_the_type_and_the_expiry() -> None:
    client = StubS3()

    url = R2ObjectStore(_settings(), client=client).presign_put(
        object_key=OBJECT_KEY,
        content_type="audio/mpeg",
        expires_in=3600,
    )

    assert url.startswith("https://bucket.test/signed")
    assert client.calls == [
        {
            "operation": "put_object",
            "Params": {"Bucket": BUCKET, "Key": OBJECT_KEY, "ContentType": "audio/mpeg"},
            "ExpiresIn": 3600,
        }
    ]


def test_presigning_a_download_signs_one_key_and_names_the_file() -> None:
    """The GET is scoped to one key, and the saved name travels with the signature.

    ``ResponseContentDisposition`` is a *param*, not a header we serve: the download is a
    conversation between the browser and the bucket, so the name has to be inside the
    thing being signed or it does not happen at all.
    """
    client = StubS3()

    url = R2ObjectStore(_settings(), client=client).presign_get(
        object_key=MIDI_KEY,
        expires_in=300,
        filename="Midnight Drive.mid",
    )

    assert url.startswith("https://bucket.test/signed")
    assert client.calls == [
        {
            "operation": "get_object",
            "Params": {
                "Bucket": BUCKET,
                "Key": MIDI_KEY,
                "ResponseContentDisposition": 'attachment; filename="Midnight Drive.mid"',
            },
            "ExpiresIn": 300,
        }
    ]


def test_a_download_with_no_name_asks_for_no_override() -> None:
    """Absent rather than empty: an empty disposition header is not a header."""
    client = StubS3()

    R2ObjectStore(_settings(), client=client).presign_get(object_key=MIDI_KEY, expires_in=60)

    assert client.calls == [
        {"operation": "get_object", "Params": {"Bucket": BUCKET, "Key": MIDI_KEY}, "ExpiresIn": 60}
    ]


# --- Configuration -----------------------------------------------------------


@pytest.mark.parametrize("missing", ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"])
def test_storage_that_is_not_configured_names_the_setting_that_is_missing(missing: str) -> None:
    store = R2ObjectStore(_settings(**{missing: ""}), client=StubS3())

    problem = _refused(lambda: store.head(object_key=OBJECT_KEY))

    assert problem.status == 500
    assert problem.code is ErrorCode.SERVER_MISCONFIGURED
    assert missing in problem.message


def test_a_store_that_is_not_configured_never_reaches_the_bucket() -> None:
    client = StubS3()
    store = R2ObjectStore(_settings(R2_SECRET_ACCESS_KEY=""), client=client)

    _refused(
        lambda: store.presign_put(
            object_key=OBJECT_KEY,
            content_type="audio/mpeg",
            expires_in=60,
        )
    )

    assert client.calls == []


def test_the_endpoint_is_cloudflares_unless_it_is_overridden() -> None:
    """The client's own view of where a request would go."""
    default = R2ObjectStore(_settings())
    local = R2ObjectStore(_settings(R2_ENDPOINT_URL=ENDPOINT_OVERRIDE))

    assert default._client.meta.endpoint_url == "https://test-account.r2.cloudflarestorage.com"
    assert local._client.meta.endpoint_url == ENDPOINT_OVERRIDE
