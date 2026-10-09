"""Request and response contracts for the upload lifecycle.

The JSON surface of ``public.uploads``, plus the two operations performed on it.
Field names mirror the columns; the API's own vocabulary (``upload_url``,
``max_bytes``) only appears where the table has no equivalent.

Validation is split on purpose. Types and shapes are Pydantic's; the product rules
(which extensions, how large) live in ``app/services/uploads.py``, so one rule
serves the presign request, the object that actually landed, and the tests.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from app.schemas.analysis_job import AnalysisJobOut
from app.schemas.song import SongOut
from app.services.upload_rules import MAX_UPLOAD_BYTES
from pydantic import BaseModel, ConfigDict, Field

# A filename becomes part of an object key, so it is bounded before it is used.
FilenameField = Annotated[str, Field(min_length=1, max_length=255)]

# A sha256 digest is exactly 64 lowercase hex characters
# (`uploads_checksum_expected_check`); the service lowercases the rest.
ChecksumField = Annotated[str, Field(min_length=64, max_length=64)]


class PresignRequest(BaseModel):
    """What the browser is about to upload.

    ``bytes`` and ``checksum_sha256`` are optional: the size is enforced again
    against the object itself at completion, so a client that cannot compute a
    digest is not locked out. Declaring them lets the API refuse before the
    upload rather than after it.
    """

    filename: FilenameField
    content_type: str | None = Field(default=None, max_length=128)
    bytes: int | None = Field(default=None, gt=0)
    checksum_sha256: ChecksumField | None = None


class UploadOut(BaseModel):
    """One upload as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    song_id: UUID | None
    object_key: str
    status: str
    declared_bytes: int | None
    declared_content_type: str | None
    bytes_actual: int | None
    content_type_actual: str | None
    etag_actual: str | None
    expires_at: datetime
    completed_at: datetime | None
    created_at: datetime


class PresignResponse(BaseModel):
    """Everything the browser needs to PUT the file, and nothing more.

    ``headers`` is what the browser must send for the signature to hold - the
    presigned PUT signs ``Content-Type``.
    """

    upload: UploadOut
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    max_bytes: int = MAX_UPLOAD_BYTES


class CompleteRequest(BaseModel):
    """Which upload finished, and what the resulting song should be called."""

    upload_id: UUID
    title: str | None = Field(default=None, max_length=200)
    artist: str | None = Field(default=None, max_length=200)
    project_id: UUID | None = None


class CompleteResponse(BaseModel):
    """What a completed upload became, including the job it just queued."""

    upload: UploadOut
    song: SongOut
    job: AnalysisJobOut | None = None
