"""What a finished analysis leaves behind: rows, and objects in the bucket.

A job produces two kinds of thing. The small digests - tempo, key, how many notes the
transcription found, the song's chord progression - live inline in ``analysis_results.summary``.
The two payloads far too big for that column - the MIDI file and the chord timeline - go to the
bucket, each referenced by its own ``object_key``. This module is the only place either shape is
decided, so "what a result looks like" is one file to read.

Both keys are derived, never invented: ``users/<user id>/analysis/<job id>/<filename>``. That
satisfies ``analysis_results_object_key_check`` - asserted in the tests, because a key the
database would refuse is a bug that only ever shows up on the happy path - it stays inside the
owner's own prefix, and it is stable for a job, which is what makes writing it a second time an
overwrite instead of a duplicate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.analysis_result import ResultInput
from app.services.storage import ObjectStore
from app.workers import chord_summary

if TYPE_CHECKING:
    # Typing only: importing the audio stack here would make this module (and the
    # pipeline) unusable without it being installed.
    from app.workers.analysis import AudioAnalysis
    from app.workers.chords import ChordTimeline
    from app.workers.midi import Transcription

# What each artifact is stored as, mirrored by `analysis_results.object_content_type`.
MIDI_CONTENT_TYPE = "audio/midi"
# JSON, and not the newline-delimited form the seed's fixture imagines: the only reader is
# `ObjectStore.download`, which hands back whole bytes and cannot stream a line at a time.
CHORDS_CONTENT_TYPE = "application/json"

# The directory segment between the owner and the job, so a user's uploads and the
# things derived from them are distinguishable in a listing.
ANALYSIS_PREFIX = "analysis"
TRANSCRIPTION_FILENAME = "transcription.mid"
CHORDS_FILENAME = "chords.json"


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


@dataclass(frozen=True, slots=True)
class StoredChords:
    """Where the chord timeline went, and the digest of what is inside it.

    The digest is what goes inline in the row: a handful of numbers and the song's progression,
    which is everything a library row needs and nothing the timeline itself has to be fetched
    for.
    ``progression`` is a tuple so this stays hashable and comparable, and it arrives already
    duration-ordered (:func:`app.workers.chord_summary.progression`).
    """

    object_key: str
    object_bytes: int
    content_type: str
    detector: str
    vocabulary: str
    segment_count: int
    progression: tuple[str, ...]
    confidence: float
    no_chord_ratio: float


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


def chords_object_key(*, user_id: UUID, job_id: UUID) -> str:
    """``users/<user id>/analysis/<job id>/chords.json`` (see :func:`midi_object_key`)."""
    return f"users/{user_id}/{ANALYSIS_PREFIX}/{job_id}/{CHORDS_FILENAME}"


def encode_chords(timeline: ChordTimeline) -> bytes:
    """The timeline as the JSON object the bucket holds and the API serves back.

    One array of segments rather than one object per segment: the reader is a single GET that
    hands back whole bytes, so there is nothing to stream and no reason to make the payload any
    harder to read than it is.
    """
    payload = {
        "detector": timeline.name,
        "vocabulary": timeline.vocabulary,
        "key": timeline.key,
        "hop_ms": timeline.hop_ms,
        "segments": [
            {
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "chord": segment.chord,
                "confidence": segment.confidence,
            }
            for segment in timeline.segments
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def store_chords(
    store: ObjectStore,
    *,
    user_id: UUID,
    job_id: UUID,
    timeline: ChordTimeline,
) -> StoredChords:
    """Put the chord timeline in the bucket, and describe where it landed.

    The digest is measured from the timeline's own segments here rather than accepted beside it, so
    a row can never describe a different timeline from the one that was actually written.
    """
    key = chords_object_key(user_id=user_id, job_id=job_id)
    info = store.put_bytes(
        object_key=key,
        body=encode_chords(timeline),
        content_type=CHORDS_CONTENT_TYPE,
    )

    return StoredChords(
        object_key=key,
        object_bytes=info.bytes,
        content_type=CHORDS_CONTENT_TYPE,
        detector=timeline.name,
        vocabulary=timeline.vocabulary,
        segment_count=chord_summary.segment_count(timeline.segments),
        progression=chord_summary.progression(timeline.segments),
        confidence=chord_summary.confidence(timeline.segments),
        no_chord_ratio=chord_summary.silence_ratio(timeline.segments),
    )


def build_results(
    *,
    analysis: AudioAnalysis,
    midi: StoredMidi,
    chords: StoredChords,
) -> list[ResultInput]:
    """The rows a succeeded job writes: one per artifact kind it produced.

    Duration is deliberately absent: it is a column on ``songs`` rather than an artifact, and
    storing the same number in two places is how they drift. Sections are not produced yet, and a
    row claiming an empty one would be a lie the UI has to learn to ignore.

    ``key`` is repeated in the chords digest on purpose. The row is read on its own - the library
    shows a progression without fetching the song - and a digest that needed a join to be
    interpretable would not be a digest.
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
            kind="chords",
            summary={
                "detector": chords.detector,
                "vocabulary": chords.vocabulary,
                "key": analysis.musical_key,
                "segments": chords.segment_count,
                "progression": list(chords.progression),
                "confidence": chords.confidence,
                "no_chord_ratio": chords.no_chord_ratio,
            },
            object_key=chords.object_key,
            object_bytes=chords.object_bytes,
            object_content_type=chords.content_type,
        ),
        ResultInput(
            kind="midi",
            summary={
                "notes": midi.note_count,
                "window_seconds": midi.window_seconds,
                "transcriber": midi.transcriber,
            },
            object_key=midi.object_key,
            object_bytes=midi.object_bytes,
            object_content_type=midi.content_type,
        ),
    ]
