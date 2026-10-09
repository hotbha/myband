"""The API's single error shape.

Every failure the browser can see is ``{"detail": {"code": ..., "message": ...}}``
with an HTTP status that matches:

* ``code`` is a stable, machine-readable string from :class:`ErrorCode`. The web
  app switches on it; it does not parse messages.
* ``message`` is a sentence for a human. It never contains a stack trace, a
  credential or a database error, because it is rendered in the UI.

The services raise :class:`ApiProblem` directly rather than translating domain
errors in the routes. These rejections are user-facing by nature - "that is not an
MP3" is a product answer, not an internal detail - and one exception type with a
status attached is less machinery than a translation layer would be.
"""

from enum import StrEnum
from http import HTTPStatus


class ErrorCode(StrEnum):
    """Machine-readable reasons. Adding one is a compatible change; renaming is not."""

    # --- Caller/authentication ---
    UNAUTHENTICATED = "unauthenticated"
    INVALID_REQUEST = "invalid_request"
    INVALID_FILENAME = "invalid_filename"

    # --- The file itself ---
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    FILE_TOO_LARGE = "file_too_large"

    # --- Upload lifecycle ---
    UPLOAD_NOT_FOUND = "upload_not_found"
    UPLOAD_NOT_PENDING = "upload_not_pending"
    UPLOAD_EXPIRED = "upload_expired"
    OBJECT_NOT_FOUND = "object_not_found"
    OBJECT_EMPTY = "object_empty"

    # --- Other resources ---
    SONG_NOT_FOUND = "song_not_found"
    JOB_NOT_FOUND = "job_not_found"
    PROJECT_NOT_FOUND = "project_not_found"

    # --- Our side ---
    STORAGE_UNAVAILABLE = "storage_unavailable"
    # The bucket answered, and refused: a request its policy will not accept (a content
    # type outside `allowed_mime_types`, say). Nothing about waiting changes that.
    STORAGE_REJECTED = "storage_rejected"
    AUTH_UNAVAILABLE = "auth_unavailable"
    SERVER_MISCONFIGURED = "server_misconfigured"


class ApiProblem(Exception):
    """An error the caller is allowed to see, with the status it maps to."""

    def __init__(self, status: HTTPStatus, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def body(self) -> dict[str, dict[str, str]]:
        """The JSON body, ready for ``JSONResponse``."""
        return {"detail": {"code": self.code.value, "message": self.message}}
