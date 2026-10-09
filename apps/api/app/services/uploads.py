"""The upload lifecycle: what a browser may PUT, and what that becomes.

Two operations, and the rules that make them safe to expose:

* :func:`start_upload` validates what was asked for, writes the ``uploads`` row and
  signs a PUT URL for it. The row exists before any URL does, so a URL can never
  point at a key nobody authorized, and an abandoned attempt stays visible to the
  sweeper.
* :func:`complete_upload` asks the bucket what actually landed, and turns it into a
  song plus a queued analysis job in one transaction: the upload's transition, the
  song, the claim and the job all commit together or not at all.

Nothing here commits - the caller owns the transaction boundary, the way
``app/services/queue.py`` does - and nothing here reads audio bytes. The size and
the MIME type used to build the song are the bucket's answer to a HEAD, not the
browser's word.

Re-completing an upload that already produced a song returns that same song and
job (``created=False``): a double click or a retried request must not create a
second song, and ``uploads_claim_key`` would refuse one anyway.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import UUID

import psycopg
from app.core.config import get_settings
from app.core.ids import new_id
from app.core.problems import ApiProblem, ErrorCode
from app.models import analysis_job, project, song
from app.models import upload as upload_model
from app.models.analysis_job import AnalysisJob
from app.models.song import Song
from app.models.upload import Upload
from app.services import queue
from app.services.storage import ObjectInfo, ObjectStore
from app.services.upload_rules import (
    build_object_key,
    check_declared_bytes,
    check_object,
    extension_of,
    normalize_checksum,
    normalize_filename,
    normalize_title,
    resolve_content_type,
    title_from_key,
)

# The rules this flow applies - sizes, extensions, object keys, titles - live in
# `app/services/upload_rules.py`, so they can be read and tested without a
# connection, a bucket or a clock.


@dataclass(frozen=True, slots=True)
class StartedUpload:
    """A pending upload plus the URL that can fill it."""

    upload: Upload
    upload_url: str
    content_type: str


@dataclass(frozen=True, slots=True)
class CompletedUpload:
    """What a completed upload became.

    ``created`` is ``False`` when this call found the work already done and is
    reporting the first result.
    """

    upload: Upload
    song: Song
    job: AnalysisJob | None
    created: bool


def start_upload(
    conn: psycopg.Connection,
    *,
    store: ObjectStore,
    user_id: UUID,
    filename: str,
    content_type: str | None = None,
    declared_bytes: int | None = None,
    checksum_sha256: str | None = None,
    now: datetime | None = None,
) -> StartedUpload:
    """Validate the request, write the pending row, sign the URL for it."""
    settings = get_settings()
    accepted_name = normalize_filename(filename)
    extension = extension_of(accepted_name)
    resolved_type = resolve_content_type(extension, content_type)
    check_declared_bytes(declared_bytes)
    expected_checksum = normalize_checksum(checksum_sha256)

    upload_id = new_id()
    object_key = build_object_key(user_id=user_id, upload_id=upload_id, filename=accepted_name)
    ttl_seconds = settings.upload_url_ttl_seconds
    expires_at = (now or datetime.now(UTC)) + timedelta(seconds=ttl_seconds)

    upload_url = store.presign_put(
        object_key=object_key,
        content_type=resolved_type,
        expires_in=ttl_seconds,
    )
    upload = upload_model.create_pending(
        conn,
        upload_id=upload_id,
        user_id=user_id,
        object_key=object_key,
        expires_at=expires_at,
        declared_bytes=declared_bytes,
        declared_content_type=resolved_type,
        checksum_expected=expected_checksum,
    )
    return StartedUpload(upload=upload, upload_url=upload_url, content_type=resolved_type)


def complete_upload(
    conn: psycopg.Connection,
    *,
    store: ObjectStore,
    user_id: UUID,
    upload_id: UUID,
    title: str | None = None,
    artist: str | None = None,
    project_id: UUID | None = None,
    now: datetime | None = None,
) -> CompletedUpload:
    """Turn a finished upload into a song and a queued analysis job.

    The bucket decides what is true: size, content type and ETag come from a HEAD,
    and a request that no longer matches the row's state is refused rather than
    repaired. Everything written here happens in the caller's transaction.
    """
    current = _visible_upload(conn, upload_id=upload_id, user_id=user_id)

    already_done = _replay(conn, upload=current, user_id=user_id)
    if already_done is not None:
        return already_done

    _check_claimable(current, now=now)
    info = _object_info(store, upload=current)
    check_object(info)
    content_type = resolve_content_type(
        extension_of(current.object_key),
        info.content_type or current.declared_content_type,
    )
    check_project(conn, project_id=project_id, user_id=user_id)

    completed = upload_model.complete(
        conn,
        upload_id=current.id,
        bytes_actual=info.bytes,
        completed_at=now or datetime.now(UTC),
        content_type_actual=content_type,
        etag_actual=info.etag,
    )
    if completed is None:
        # Lost the compare-and-swap between the read above and here: another
        # request for the same upload got there first.
        raced = _replay(
            conn,
            upload=_visible_upload(conn, upload_id=upload_id, user_id=user_id),
            user_id=user_id,
        )
        if raced is not None:
            return raced
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.UPLOAD_NOT_PENDING,
            "This upload is already being completed.",
        )

    created_song = song.insert(
        conn,
        user_id=user_id,
        project_id=project_id,
        title=normalize_title(title) or title_from_key(current.object_key),
        artist=artist,
        source_object_key=current.object_key,
        source_checksum=current.checksum_expected,
        source_bytes=info.bytes,
        source_content_type=content_type,
    )
    claimed = upload_model.claim_for_song(conn, upload_id=current.id, song_id=created_song.id)
    if claimed is None:
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.UPLOAD_NOT_PENDING,
            "This upload is already attached to a song.",
        )

    return CompletedUpload(
        upload=claimed,
        song=created_song,
        job=enqueue_analysis(conn, user_id=user_id, created_song=created_song, upload=claimed),
        created=True,
    )


def enqueue_analysis(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    created_song: Song,
    upload: Upload,
) -> AnalysisJob | None:
    """Queue the first analysis for a song, and hand back the job in flight.

    A song created one statement ago cannot already have work in flight, so the
    fallback is belt-and-braces - but a retried request can reach here, and the
    caller wants a job id either way. ``enqueue`` returns the job already there
    when the partial unique index refuses a second one.
    """
    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=created_song.id,
        pipeline_version=get_settings().pipeline_version,
        source_object_key=upload.object_key,
        source_checksum=upload.checksum_expected,
    )
    return outcome.job or analysis_job.get_active_for_song(conn, created_song.id)


def latest_job(conn: psycopg.Connection, song_id: UUID) -> AnalysisJob | None:
    """The song's job in flight, or its most recent one.

    This is what the library shows. It cannot come from ``songs.latest_job_id``,
    which only moves when a job succeeds - a queued job would stay invisible.
    """
    active = analysis_job.get_active_for_song(conn, song_id)
    if active is not None:
        return active

    history = analysis_job.list_for_song(conn, song_id, limit=1)
    return history[0] if history else None


def _visible_upload(conn: psycopg.Connection, *, upload_id: UUID, user_id: UUID) -> Upload:
    """The caller's upload, or a 404.

    Another account's upload answers exactly like a missing one: the API never
    confirms that a row it will not show you exists.
    """
    found = upload_model.get(conn, upload_id)
    if found is None or found.user_id != user_id:
        raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.UPLOAD_NOT_FOUND, "No such upload.")
    return found


def _replay(conn: psycopg.Connection, *, upload: Upload, user_id: UUID) -> CompletedUpload | None:
    """The result of a completion that already happened, if it did."""
    if upload.status != "completed":
        return None

    if upload.song_id is None:
        # Unreachable by construction - the completion and the claim are one
        # transaction - so treat it as a broken row instead of inventing a song.
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.UPLOAD_NOT_PENDING,
            "This upload is completed but not attached to a song.",
        )

    existing = song.get(conn, upload.song_id)
    if existing is None or existing.user_id != user_id:
        raise ApiProblem(
            HTTPStatus.NOT_FOUND,
            ErrorCode.SONG_NOT_FOUND,
            "That song no longer exists.",
        )

    return CompletedUpload(
        upload=upload,
        song=existing,
        job=latest_job(conn, existing.id),
        created=False,
    )


def _check_claimable(upload: Upload, *, now: datetime | None) -> None:
    """Refuse an upload that is not pending, or whose URL has lapsed."""
    if upload.status == "aborted":
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.UPLOAD_NOT_PENDING,
            "This upload was aborted.",
        )
    if upload.status == "expired" or upload.expires_at <= (now or datetime.now(UTC)):
        raise ApiProblem(
            HTTPStatus.GONE,
            ErrorCode.UPLOAD_EXPIRED,
            "This upload expired before it finished. Start a new one.",
        )


def check_project(conn: psycopg.Connection, *, project_id: UUID | None, user_id: UUID) -> None:
    """A song may only be filed into the caller's own project.

    The database asserts the same thing in ``songs_update_own``; the API checks it
    itself because it writes as ``postgres``, which bypasses RLS. Filing a song
    into someone else's project would leak their library through the join that
    renders it (docs/schema.md).
    """
    if project_id is None:
        return

    owned = project.get(conn, project_id)
    if owned is None or owned.owner_id != user_id or owned.deleted_at is not None:
        raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.PROJECT_NOT_FOUND, "No such project.")


def _object_info(store: ObjectStore, *, upload: Upload) -> ObjectInfo:
    """What the bucket holds, or a 409 when the PUT never happened."""
    info = store.head(object_key=upload.object_key)
    if info is None:
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.OBJECT_NOT_FOUND,
            "The audio never arrived in storage. Upload it again.",
        )
    return info


def get_upload(conn: psycopg.Connection, *, upload_id: UUID, user_id: UUID) -> Upload:
    """One of the caller's uploads, or a 404. The read path for ``GET /uploads/{id}``."""
    return _visible_upload(conn, upload_id=upload_id, user_id=user_id)
