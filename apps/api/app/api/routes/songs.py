"""Song routes: the library, one song's analysis, its MIDI, its chords, and its sections."""

import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from app.api.deps import CurrentUserId, StorageDep
from app.core.config import get_settings
from app.core.db import connect
from app.core.problems import ApiProblem, ErrorCode
from app.models import analysis_job, analysis_result
from app.models import song as song_model
from app.schemas.song import (
    ChordsOut,
    MidiDownloadOut,
    SectionsOut,
    SongListOut,
    SongWithJob,
    chords_view,
    sections_view,
    song_view,
)
from app.services import upload_rules, uploads
from fastapi import APIRouter, Query

router = APIRouter(tags=["songs"])

# Bounds on a library page: enough to fill a screen, small enough that one request
# cannot ask for the whole account's history.
DEFAULT_LIBRARY_LIMIT = 50
MAX_LIBRARY_LIMIT = 100

LibraryLimit = Annotated[int, Query(ge=1, le=MAX_LIBRARY_LIMIT)]

# The artifact a MIDI download is a download of.
MIDI_KIND = "midi"

# The artifact a chord view is a view of.
CHORDS_KIND = "chords"

# The artifact a section view is a view of.
SECTIONS_KIND = "sections"

# What the file is called when the song's title leaves nothing usable, and what the
# extension is either way. The fallback matches the object's own name in the bucket.
FALLBACK_MIDI_FILENAME = "transcription.mid"
MIDI_EXTENSION = ".mid"


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


def _download_filename(title: str) -> str:
    """A name for the saved file, built from the song's title.

    The name becomes a response header on the object and then a filename in someone's
    Downloads folder, and a title is user input - so anything outside the alphabet the
    object-key rule already allows is replaced rather than passed through. A quote or a
    newline in a header is a header the browser cannot parse, and this is the shortest way
    to be sure of that.
    """
    safe = upload_rules.UNSAFE_FILENAME_CHARS.sub("_", title.strip()).strip("._-")
    if not safe:
        return FALLBACK_MIDI_FILENAME

    room = upload_rules.MAX_FILENAME_LENGTH - len(MIDI_EXTENSION)
    return f"{safe[:room]}{MIDI_EXTENSION}"


@router.get("/songs/{song_id}/midi")
def download_song_midi(
    song_id: UUID,
    user_id: CurrentUserId,
    store: StorageDep,
) -> MidiDownloadOut:
    """A short-lived URL for the song's MIDI, or a 404 that says why.

    The URL and not the bytes: the object is private, so the only way a browser can read
    it is with a signature this service produced after checking that the caller owns the
    song. The signature is scoped to one key and expires in minutes, which is what makes a
    leaked link a small problem rather than a permanent one.

    JSON rather than a 302 because of who fetches it: the browser client asks for this with
    a token, then sends the tab to the URL it gets back. A redirect would be followed by
    the fetch, not by the tab, and the client would end up reading the MIDI into memory
    instead of handing the user a file.

    Every refusal is a 404, because there is nothing to download yet either way and the
    screen already shows the job's status. The messages differ, though: one says the song
    has not been analysed, the other that its analysis produced no MIDI.
    """
    with connect() as conn:
        song = song_model.get(conn, song_id)
        if song is None or song.user_id != user_id or song.deleted_at is not None:
            raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.SONG_NOT_FOUND, "No such song.")

        if song.latest_job_id is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song has not been analysed yet.",
            )

        artifact = analysis_result.get_for_job_kind(
            conn,
            job_id=song.latest_job_id,
            kind=MIDI_KIND,
        )
        if artifact is None or artifact.object_key is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song's analysis produced no MIDI file.",
            )

        object_key = artifact.object_key

    ttl = get_settings().download_url_ttl_seconds
    url = store.presign_get(
        object_key=object_key,
        expires_in=ttl,
        filename=_download_filename(song.title),
    )

    return MidiDownloadOut(url=url, expires_at=datetime.now(UTC) + timedelta(seconds=ttl))


@router.get("/songs/{song_id}/chords")
def get_song_chords(
    song_id: UUID,
    user_id: CurrentUserId,
    store: StorageDep,
) -> ChordsOut:
    """The song's chord timeline, or a 404 that says why.

    The timeline itself rather than a signed link, which is the one place this differs from the MIDI
    next door: a screen reads this, so signing a URL would cost a second round trip and hand the
    browser a link that expires while it is still on that screen.

    Every refusal is a 404 carrying ``analysis_not_ready``, because there is nothing to show either
    way and the screen already reports the job's status. The messages differ, though, so a reader
    can tell "not analysed yet" from "analysed, and it produced no chords" from "the object is
    gone" - which are three different problems with three different answers.

    Reading the object is the one thing this route does that the MIDI route does not: the payload is
    the answer, so it is fetched here rather than handed to the caller as a URL to fetch.
    """
    with connect() as conn:
        song = song_model.get(conn, song_id)
        if song is None or song.user_id != user_id or song.deleted_at is not None:
            raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.SONG_NOT_FOUND, "No such song.")

        if song.latest_job_id is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song has not been analysed yet.",
            )

        artifact = analysis_result.get_for_job_kind(
            conn,
            job_id=song.latest_job_id,
            kind=CHORDS_KIND,
        )
        if artifact is None or artifact.object_key is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song's analysis produced no chords.",
            )

        object_key = artifact.object_key
        summary = artifact.summary

    payload = store.download(object_key=object_key)
    if payload is None:
        # The row exists and the object does not. Reachable in practice: the seed writes a chords
        # row for a fixture whose object was never uploaded, and a garbage-collected object leaves
        # the same hole if it is swept before its row.
        raise ApiProblem(
            HTTPStatus.NOT_FOUND,
            ErrorCode.ANALYSIS_NOT_READY,
            "This song's chords are no longer in storage.",
        )

    return chords_view(json.loads(payload), summary)


@router.get("/songs/{song_id}/sections")
def get_song_sections(
    song_id: UUID,
    user_id: CurrentUserId,
    store: StorageDep,
) -> SectionsOut:
    """The song's sections, or a 404 that says why.

    The same route the chord timeline has, over the artifact next to it, and it refuses in the
    same three ways with the same code: ``analysis_not_ready`` for a song nothing has analysed,
    for one whose analysis produced no sections, and for one whose list is no longer in the
    bucket. The messages differ so a reader can tell those three apart; the screen reports the
    job's own status either way.

    Sections cover a whole recording by construction, so there is no coverage to report here -
    the interesting number is the form, and that is in the digest the worker wrote.
    """
    with connect() as conn:
        song = song_model.get(conn, song_id)
        if song is None or song.user_id != user_id or song.deleted_at is not None:
            raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.SONG_NOT_FOUND, "No such song.")

        if song.latest_job_id is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song has not been analysed yet.",
            )

        artifact = analysis_result.get_for_job_kind(
            conn,
            job_id=song.latest_job_id,
            kind=SECTIONS_KIND,
        )
        if artifact is None or artifact.object_key is None:
            raise ApiProblem(
                HTTPStatus.NOT_FOUND,
                ErrorCode.ANALYSIS_NOT_READY,
                "This song's analysis produced no sections.",
            )

        object_key = artifact.object_key
        summary = artifact.summary

    payload = store.download(object_key=object_key)
    if payload is None:
        # The same hole the chord route answers for: a row whose object is gone.
        raise ApiProblem(
            HTTPStatus.NOT_FOUND,
            ErrorCode.ANALYSIS_NOT_READY,
            "This song's sections are no longer in storage.",
        )

    return sections_view(json.loads(payload), summary)
