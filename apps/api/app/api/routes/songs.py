"""Song routes: the library, and one song's current analysis."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from app.api.deps import CurrentUserId
from app.core.db import connect
from app.core.problems import ApiProblem, ErrorCode
from app.models import analysis_job
from app.models import song as song_model
from app.schemas.song import SongListOut, SongWithJob, song_view
from app.services import uploads
from fastapi import APIRouter, Query

router = APIRouter(tags=["songs"])

# Bounds on a library page: enough to fill a screen, small enough that one request
# cannot ask for an account's whole history.
DEFAULT_LIBRARY_LIMIT = 50
MAX_LIBRARY_LIMIT = 100

LibraryLimit = Annotated[int, Query(ge=1, le=MAX_LIBRARY_LIMIT)]


@router.get("/songs")
def list_songs(user_id: CurrentUserId, limit: LibraryLimit = DEFAULT_LIBRARY_LIMIT) -> SongListOut:
    """The caller's library, newest first, with what is happening to each song.

    Two queries whatever the page size: the songs, then the in-flight jobs for
    exactly those songs (``analysis_jobs_one_active_per_song_key`` allows at most
    one each). A song with no job in flight reports ``job: null`` - the UI reads
    ``latest_job_id`` for "has ever been analysed".
    """
    with connect() as conn:
        songs = song_model.list_for_user(conn, user_id, limit=limit)
        active = {
            job.song_id: job
            for job in analysis_job.list_active_for_songs(conn, [song.id for song in songs])
        }

    return SongListOut(songs=[song_view(song, active.get(song.id)) for song in songs])


@router.get("/songs/{song_id}")
def get_song(song_id: UUID, user_id: CurrentUserId) -> SongWithJob:
    """One song and its current job.

    Unlike the list, this job is the most recent analysis even when it has
    finished - which is how a failure becomes visible.
    """
    with connect() as conn:
        found = song_model.get(conn, song_id)
        if found is None or found.user_id != user_id or found.deleted_at is not None:
            raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.SONG_NOT_FOUND, "No such song.")

        job = uploads.latest_job(conn, found.id)

    return song_view(found, job)
