"""What a finished analysis leaves behind: rows, and an object in the bucket.

A job produces two kinds of thing. The small digests - tempo, key, how many notes the
transcription found - live inline in ``analysis_results.summary``. The MIDI file is far
too big for that column and goes to the bucket, referenced by ``object_key``. This
module is the only place either shape is decided, so "what a result looks like" is one
file to read.

The MIDI key is derived, never invented: ``users/<user id>/analysis/<job id>/``. That
satisfies ``analysis_results_object_key_check`` - asserted in the tests, because a key
the database would refuse is a bug that only ever shows up on the happy path - it stays
inside the owner's own prefix, and it is stable for a job, which is what makes writing
it a second time an overwrite instead of a duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.analysis_result import ResultInput
from app.services.storage import ObjectStore

if TYPE_CHECKING:
    # Typing only: importing the audio stack here would make this module (and the
    # pipeline) unusable without it being installed.
    from app.workers.analysis import AudioAnalysis
    from app.workers.midi import Transcription

# What the artifact is stored as, mirrored by `analysis_results.object_content_type`.
MIDI_CONTENT_TYPE = "audio/midi"

# The directory segment between the owner and the job, so a user's uploads and the
# things derived from them are distinguishable in a listing.
ANALYSIS_PREFIX = "analysis"
TRANSCRIPTION_FILENAME = "transcription.mid"


@dataclass(frozen=True, slots=True)
class StoredMidi:
    """Where the MIDI went, and what it took to produce it.

    Carries the provenance (``transcriber``, ``window_seconds``) as well as the
    location, because that is what goes into the row's inline summary.
    """

    object_key: str
    object_bytes: int
    content_type: str
    note_count: int
    window_seconds: int
    transcriber: str


def midi_object_key(*, user_id: UUID, job_id: UUID) -> str:
    """``users/<user id>/analysis/<job id>/transcription.mid``.

    Derived from the same two ids the row is keyed by, so two runs of the same job
    write the same key and nothing has to be looked up to find it again.
    """
    return f"users/{user_id}/{ANALYSIS_PREFIX}/{job_id}/{TRANSCRIPTION_FILENAME}"


def store_midi(
    store: ObjectStore,
    *,
    user_id: UUID,
    job_id: UUID,
    transcription: Transcription,
) -> StoredMidi:
    """Put the MIDI in the bucket, and describe where it landed.

    ``object_bytes`` is the bucket's own answer rather than ``len(data)``: the row and
    the object have to agree, and only one of the two can be asked. Overwriting an
    existing key is the intended behaviour - it is what makes a re-run idempotent.
    """
    key = midi_object_key(user_id=user_id, job_id=job_id)
    info = store.put_bytes(
        object_key=key,
        body=transcription.data,
        content_type=MIDI_CONTENT_TYPE,
    )

    return StoredMidi(
        object_key=key,
        object_bytes=info.bytes,
        content_type=MIDI_CONTENT_TYPE,
        note_count=transcription.note_count,
        window_seconds=transcription.window_seconds,
        transcriber=transcription.name,
    )


def build_results(*, analysis: AudioAnalysis, stored: StoredMidi) -> list[ResultInput]:
    """The rows a succeeded job writes: one per artifact kind it produced.

    Duration is deliberately absent: it is a column on ``songs`` rather than an
    artifact, and storing the same number in two places is how they drift. Chords and
    sections are not produced yet, and a row claiming an empty one would be a lie the
    UI has to learn to ignore.
    """
    return [
        ResultInput(
            kind="bpm",
            summary={"bpm": round(analysis.bpm, 2), "beats": analysis.beats},
        ),
        ResultInput(
            kind="key",
            summary={"key": analysis.musical_key, "strength": round(analysis.key_strength, 3)},
        ),
        ResultInput(
            kind="midi",
            summary={
                "notes": stored.note_count,
                "window_seconds": stored.window_seconds,
                "transcriber": stored.transcriber,
            },
            object_key=stored.object_key,
            object_bytes=stored.object_bytes,
            object_content_type=stored.content_type,
        ),
    ]
