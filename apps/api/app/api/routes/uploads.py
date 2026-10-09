"""Upload routes: the HTTP surface of ``app/services/uploads.py``.

Each route owns its transaction (see ``app/api/deps.py`` for why that is not a
dependency): the ``with connect()`` block commits before the response is built, so
a caller is never told "created" about work that rolled back.
"""

from uuid import UUID

from app.api.deps import CurrentUserId, StorageDep
from app.core.db import connect
from app.schemas.analysis_job import AnalysisJobOut
from app.schemas.song import SongOut
from app.schemas.upload import (
    CompleteRequest,
    CompleteResponse,
    PresignRequest,
    PresignResponse,
    UploadOut,
)
from app.services import uploads
from fastapi import APIRouter, Response, status

router = APIRouter(tags=["uploads"])


@router.post("/uploads/presign", status_code=status.HTTP_201_CREATED)
def presign_upload(
    body: PresignRequest,
    user_id: CurrentUserId,
    store: StorageDep,
) -> PresignResponse:
    """Record an upload and return the URL the browser fills it with.

    The API never sees the bytes: it writes a ``pending`` row, signs a PUT for
    that one key, and returns the headers the signature covers.
    """
    with connect() as conn:
        started = uploads.start_upload(
            conn,
            store=store,
            user_id=user_id,
            filename=body.filename,
            content_type=body.content_type,
            declared_bytes=body.bytes,
            checksum_sha256=body.checksum_sha256,
        )

    return PresignResponse(
        upload=UploadOut.model_validate(started.upload),
        upload_url=started.upload_url,
        headers={"Content-Type": started.content_type},
    )


@router.post("/uploads/complete", status_code=status.HTTP_201_CREATED)
def complete_upload(
    body: CompleteRequest,
    response: Response,
    user_id: CurrentUserId,
    store: StorageDep,
) -> CompleteResponse:
    """Confirm what landed in the bucket and turn the upload into a song and a job.

    Answers ``201`` when this call created the song and ``200`` when it is
    reporting one an earlier call already created - the double click case.
    """
    with connect() as conn:
        outcome = uploads.complete_upload(
            conn,
            store=store,
            user_id=user_id,
            upload_id=body.upload_id,
            title=body.title,
            artist=body.artist,
            project_id=body.project_id,
        )

    if not outcome.created:
        response.status_code = status.HTTP_200_OK

    return CompleteResponse(
        upload=UploadOut.model_validate(outcome.upload),
        song=SongOut.model_validate(outcome.song),
        job=None if outcome.job is None else AnalysisJobOut.model_validate(outcome.job),
    )


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: UUID, user_id: CurrentUserId) -> UploadOut:
    """One of the caller's uploads, and where it has got to."""
    with connect() as conn:
        found = uploads.get_upload(conn, upload_id=upload_id, user_id=user_id)

    return UploadOut.model_validate(found)
