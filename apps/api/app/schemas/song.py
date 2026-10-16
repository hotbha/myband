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
from app.workers import chord_summary
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


class SectionOut(BaseModel):
    """One stretch of a song, and the label it shares with the stretches that repeat it.

    Four fields, and three of them are the shape a *chord* segment arrives with - a start, an
    end and how sure the detector was - so one renderer and one shared schema can serve both.

    ``label`` is a letter rather than a name, and deliberately: ``A`` and ``B`` are the same
    music heard twice and something else heard once, which is what a detector can measure.
    Calling them verse and chorus would take lyrics, and a wrong chorus is worse than an
    honest letter (``workers.sections``).
    """

    start_ms: int
    end_ms: int
    label: str
    confidence: float


class SectionsOut(BaseModel):
    """A song's sections (``GET /songs/{id}/sections``).

    The list itself rather than a link to it, for the reason the chord timeline is: a screen
    reads this, so signing a URL would cost a second round trip and hand the browser a link
    that expires while it is still displayed.

    ``summary`` is the digest the worker wrote into ``analysis_results``, passed through
    unchanged so that the row and the response can never describe different things. The form -
    ``A B A B C`` - lives there rather than here, because it is the worker's statement about
    the list it wrote and not this contract's reading of it.

    ``hop_ms`` is the pool the detector compared, not the chroma frame: it is the grid the
    boundaries actually land on, so a client that draws them is drawing the resolution the
    detector really has.
    """

    detector: str
    vocabulary: str
    hop_ms: int
    summary: dict[str, Any]
    sections: list[SectionOut]


class ChordSegmentOut(BaseModel):
    """One chord, held for a stretch of the song (``GET /songs/{id}/chords``).

    Five fields, three of which are the shape a *section* arrives with - a start, an end and how
    sure the detector was - so one renderer and one shared schema can serve both. ``chord`` is a
    label from the product's closed vocabulary, or ``"N"`` where nothing was played.

    ``label_simple`` is that same chord as its triad: ``workers.chord_summary.simplify_label``
    applied to ``chord``, derived per response rather than stored, because the object in the bucket
    is the record of what was *detected* and this is the reading of it a screen shows by default.
    The two differ on a row where the detector heard an extension or an inversion, which is the only
    row with anything to disclose - and the browser can compare two fields without knowing a thing
    about chord grammar, or what a seventh is.
    """

    start_ms: int
    end_ms: int
    chord: str
    label_simple: str
    confidence: float


class ChordsOut(BaseModel):
    """A song's chord timeline (``GET /songs/{id}/chords``).

    The timeline itself rather than a link to it, which is the one place this differs from the MIDI
    next door: a screen reads this, so signing a URL would cost a second round trip and hand the
    browser a link that expires while it is still displayed.

    ``summary`` is the digest the worker wrote into ``analysis_results``, passed through unchanged
    so that the row and the response can never describe different things.

    Nothing is added to it for the simple view. The digest is the worker's statement about what it
    detected, and how much of the recording that accounts for; ``progression_simple`` and
    ``coverage_simple`` are *this* contract's own reading of the same timeline one level coarser, so
    they sit beside the summary rather than inside it.

    ``duration_ms`` is deliberately absent: it belongs to ``songs``, the last segment already ends
    at it, and a second copy of the same number is how two copies drift apart.
    """

    detector: str
    vocabulary: str
    key: str | None
    hop_ms: int
    summary: dict[str, Any]
    # How much of the recording the chords on the card account for, and the same for the simplified
    # spelling of them: a card covering 92% of a recording is a description of it, and one covering
    # 59% is a list of its landmarks. Derived from the timeline rather than stored, because both
    # describe a labelling the worker never wrote - and a stored copy of a derived number is how two
    # copies of it drift apart.
    coverage: float
    progression_simple: list[str]
    coverage_simple: float
    segments: list[ChordSegmentOut]


def song_view(song: Song, job: AnalysisJob | None) -> SongWithJob:
    """Build the API's view of a song and the job that is current for it."""
    return SongWithJob(**SongOut.model_validate(song).model_dump(), job=job)


def _ranked(value: Any) -> tuple[str, ...]:
    """The digest's own progression, as a tuple of labels, when the row holds one.

    Read rather than recomputed: the worker ranked those chords by how much of the song each
    occupies, and a second ranking here would be a second answer to the same question. A timeline
    written before the field existed has none, which leaves the coverage beside it measuring nothing
    - the card that would show both is not rendered either.
    """
    if not isinstance(value, list):
        return ()

    return tuple(chord for chord in value if isinstance(chord, str))


def chords_view(payload: dict[str, Any], summary: dict[str, Any]) -> ChordsOut:
    """The API's view of a stored chord timeline: what the worker wrote, plus its digest.

    The stored object is the authority on the timeline and the row is the authority on the digest,
    so this joins the two rather than recomputing either. The payload's own keys are splatted in,
    which means a stored timeline missing a field this contract promises fails loudly here instead
    of reaching a browser as ``undefined``.

    Two things here are derived rather than stored, and they are the same timeline read one level
    coarser: each row's ``label_simple``, and the card that reading produces - the same ranking the
    digest is built with, over the simplified labels, so the simple card is a restatement of this
    timeline rather than a hand-written summary of it that could drift from it. A label that is not
    a chord at all (``NO_CHORD``) simplifies to itself, so a rest stays a rest in both readings.
    """
    segments = [
        ChordSegmentOut(**segment, label_simple=chord_summary.simplify_label(segment["chord"]))
        for segment in payload["segments"]
    ]
    simple = [segment.model_copy(update={"chord": segment.label_simple}) for segment in segments]
    ranked_simple = chord_summary.progression(simple)

    return ChordsOut(
        **{**payload, "segments": segments},
        summary=summary,
        # Each card is measured against the reading it was ranked from - the detected spellings for
        # the digest's ranking, the triads for the one derived here.
        coverage=chord_summary.coverage(segments, _ranked(summary.get("progression"))),
        progression_simple=list(ranked_simple),
        coverage_simple=chord_summary.coverage(simple, ranked_simple),
    )


def sections_view(payload: dict[str, Any], summary: dict[str, Any]) -> SectionsOut:
    """The API's view of a stored section list: what the worker wrote, plus its digest.

    The stored object is the authority on the list and the row is the authority on the digest,
    so this joins the two rather than recomputing either - the same rule the chord timeline
    follows, and the reason there is no ``form`` here that could disagree with the one in the
    row.

    Nothing is derived for this response, unlike the chord timeline's simplified reading: a
    section's label is already the plainest thing that can be said about it, so there is no
    second spelling of a section to serve. The payload's own keys are splatted in, which means
    a stored list missing a field this contract promises fails loudly here instead of reaching
    a browser as ``undefined``.
    """
    return SectionsOut(
        **{**payload, "sections": [SectionOut(**section) for section in payload["sections"]]},
        summary=summary,
    )
