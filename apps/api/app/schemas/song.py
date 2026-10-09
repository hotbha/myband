"""Response contracts for ``public.songs``.

Field names mirror the columns, so the browser reads the same vocabulary the
database uses; ``user_id`` and ``deleted_at`` are left out - the caller already
knows who they are, and a soft-deleted song is answered with a 404 rather than
returned with a flag the UI has to remember to honour.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
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


class ChordSegmentOut(BaseModel):
    """One chord, held for a stretch of the song (``GET /songs/{id}/chords``).

    Four fields, and the same four a *section* will arrive with - a start, an end, a label and how
    sure the detector was - so one renderer and one shared schema can serve both. ``chord`` is a
    label from the product's closed vocabulary, or ``"N"`` where nothing was played.
    """

    start_ms: int
    end_ms: int
    chord: str
    confidence: float


class ChordsOut(BaseModel):
    """A song's chord timeline (``GET /songs/{id}/chords``).

    The timeline itself rather than a link to it, which is the one place this differs from the MIDI
    next door: a screen reads this, so signing a URL would cost a second round trip and hand the
    browser a link that expires while it is still displayed.

    ``summary`` is the digest the worker wrote into ``analysis_results``, passed through unchanged
    so that the row and the response can never describe different things.

    ``duration_ms`` is deliberately absent: it belongs to ``songs``, the last segment already ends
    at it, and a second copy of the same number is how two copies drift apart.
    """

    detector: str
    vocabulary: str
    key: str | None
    hop_ms: int
    summary: dict[str, Any]
    segments: list[ChordSegmentOut]


def song_view(song: Song, job: AnalysisJob | None) -> SongWithJob:
    """Build the API's view of a song and the job that is current for it."""
    return SongWithJob(**SongOut.model_validate(song).model_dump(), job=job)


def chords_view(payload: dict[str, Any], summary: dict[str, Any]) -> ChordsOut:
    """The API's view of a stored chord timeline: what the worker wrote, plus its digest.

    The stored object is the authority on the timeline and the row is the authority on the digest,
    so this joins the two rather than recomputing either. The payload's own keys are splatted in,
    which means a stored timeline missing a field this contract promises fails loudly here instead
    of reaching a browser as ``undefined``.
    """
    return ChordsOut(**payload, summary=summary)
