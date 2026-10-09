"""Response contracts for ``public.songs``.

Field names mirror the columns, so the browser reads the same vocabulary the
database uses; ``user_id`` and ``deleted_at`` are left out - the caller already
knows who they are, and a soft-deleted song is answered with a 404 rather than
returned with a flag the UI has to remember to honour.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.models.analysis_job import AnalysisJob
from app.models.song import Song
from app.schemas.analysis_job import AnalysisJobOut
from pydantic import BaseModel, ConfigDict


class SongOut(BaseModel):
    """One song as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    latest_job_id: UUID | None
    title: str
    artist: str | None
    duration_ms: int | None
    # The analysis headline, written by the worker when a job succeeds (migration 04).
    # Null on a song nothing has analysed yet, and on one whose analysis failed.
    bpm: Decimal | None
    musical_key: str | None
    source_object_key: str
    source_bytes: int | None
    source_content_type: str | None
    created_at: datetime
    updated_at: datetime


class SongWithJob(SongOut):
    """A song and what is currently happening to it.

    ``job`` is the analysis in flight when there is one. It cannot come from
    ``songs.latest_job_id``, which only moves when a job succeeds, so a queued job
    would stay invisible (docs/schema.md).

    The library list leaves ``job`` null for a song that is not being analysed -
    including one whose last job failed, which it does not read - so a caller that
    wants "has this ever been analysed" reads ``latest_job_id``. ``GET
    /songs/{id}`` fills ``job`` with the most recent analysis either way.
    """

    job: AnalysisJobOut | None = None


class SongListOut(BaseModel):
    """The library (``GET /songs``)."""

    songs: list[SongWithJob]


class MidiDownloadOut(BaseModel):
    """Where to fetch a song's MIDI (``GET /songs/{id}/midi``).

    A URL rather than the file: the object is private, so this service signs a
    short-lived link for it, and the browser fetches from the bucket - the same rule the
    upload follows in the other direction.

    ``expires_at`` comes from this service's clock while the URL carries the bucket's own
    ``X-Amz-Expires``. They agree because both are derived from
    ``MYBAND_DOWNLOAD_URL_TTL_SECONDS``, and the bucket's is the one that is enforced.
    """

    url: str
    expires_at: datetime


def song_view(song: Song, job: AnalysisJob | None) -> SongWithJob:
    """Build the API's view of a song and the job that is current for it."""
    return SongWithJob(**SongOut.model_validate(song).model_dump(), job=job)
