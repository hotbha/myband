"""Test doubles for the seams the API talks to.

``FakeObjectStore`` implements the ``ObjectStore`` protocol in memory: it records
what it presigned and answers a HEAD with whatever the test put there. That is what
lets the whole upload lifecycle be tested - presign, the object landing, the song,
the job - without a bucket, credentials or a network call.
"""

from app.services.storage import ObjectInfo

PRESIGN_BASE_URL = "https://bucket.test"


class FakeObjectStore:
    """An in-memory object store.

    ``presign_put`` returns a URL that names the key it signed, which is enough for
    a test to see that the key was derived from the caller. ``put`` stands in for
    the browser's upload.
    """

    def __init__(self) -> None:
        self.objects: dict[str, ObjectInfo] = {}
        self.presigned: list[dict[str, object]] = []

    def presign_put(self, *, object_key: str, content_type: str, expires_in: int) -> str:
        self.presigned.append(
            {"object_key": object_key, "content_type": content_type, "expires_in": expires_in}
        )
        return f"{PRESIGN_BASE_URL}/{object_key}?X-Amz-Expires={expires_in}"

    def head(self, *, object_key: str) -> ObjectInfo | None:
        return self.objects.get(object_key)

    def put(
        self,
        object_key: str,
        *,
        body_bytes: int,
        content_type: str = "audio/mpeg",
        etag: str | None = "5d41402abc4b2a76b9719d911017c592",
    ) -> None:
        """Stand in for the browser: the object now exists in the bucket.

        ``etag`` is the seam's value, already unquoted - stripping S3's quotes is
        the R2 adapter's job, not this fake's.
        """
        self.objects[object_key] = ObjectInfo(
            bytes=body_bytes,
            content_type=content_type,
            etag=etag,
        )

    def delete(self, object_key: str) -> None:
        """Stand in for an object expiring or being swept."""
        self.objects.pop(object_key, None)

    @property
    def last_presigned(self) -> dict[str, object]:
        """What the most recent ``presign_put`` was asked for."""
        return self.presigned[-1]
