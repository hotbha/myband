"""The shapes one analysis leaves behind: no bucket, no database, no audio.

What is asserted here is the vocabulary a stored result uses - which kinds exist, where the two
payloads go, what the inline digests say - because that vocabulary is a contract with the UI and
with every stored row. Both object keys are checked against a copy of
``analysis_results_object_key_check`` on purpose: the migration is the authority, and this is the
test that fails when the code and the CHECK drift apart.

The audio stack is deliberately absent - nothing here imports librosa - which is exactly why the
chord digest is derived by ``workers.chord_summary`` from plain segments rather than read off the
detector's own type.
"""

import json
import re

from app.core.ids import new_id
from app.models.analysis_result import MAX_SUMMARY_BYTES, ResultInput
from app.workers import artifacts
from tests.fakes import FakeAnalysis, FakeChordTimeline, FakeObjectStore, FakeTranscription

OBJECT_KEY_PATTERN = re.compile(r"^users/[0-9a-fA-F-]{36}/[A-Za-z0-9._/-]+$")


def test_the_midi_key_names_the_owner_the_job_and_the_file() -> None:
    user_id, job_id = new_id(), new_id()

    key = artifacts.midi_object_key(user_id=user_id, job_id=job_id)

    assert key == f"users/{user_id}/analysis/{job_id}/transcription.mid"
    assert OBJECT_KEY_PATTERN.fullmatch(key) is not None
    assert len(key) <= 512  # `analysis_results_object_key_check`, second half


def test_the_chords_key_is_the_midi_key_under_another_filename() -> None:
    """Both payloads hang off the same job prefix, so one job's output is one listing."""
    user_id, job_id = new_id(), new_id()

    key = artifacts.chords_object_key(user_id=user_id, job_id=job_id)

    assert key == f"users/{user_id}/analysis/{job_id}/chords.json"
    assert key == artifacts.midi_object_key(user_id=user_id, job_id=job_id).replace(
        "transcription.mid", "chords.json"
    )
    assert OBJECT_KEY_PATTERN.fullmatch(key) is not None
    assert len(key) <= 512


def test_the_keys_are_stable_for_one_job_and_different_between_jobs() -> None:
    """Idempotency starts here: a second run writes over the first run's objects."""
    user_id, job_id = new_id(), new_id()

    assert artifacts.midi_object_key(user_id=user_id, job_id=job_id) == artifacts.midi_object_key(
        user_id=user_id, job_id=job_id
    )
    assert artifacts.midi_object_key(user_id=user_id, job_id=job_id) != artifacts.midi_object_key(
        user_id=user_id, job_id=new_id()
    )
    assert artifacts.chords_object_key(
        user_id=user_id, job_id=job_id
    ) == artifacts.chords_object_key(user_id=user_id, job_id=job_id)


def test_storing_the_midi_reports_what_the_bucket_holds() -> None:
    """The row describes the object from the bucket's answer, not from a guess."""
    store = FakeObjectStore()
    transcription = FakeTranscription()

    stored = artifacts.store_midi(
        store,
        user_id=new_id(),
        job_id=new_id(),
        transcription=transcription,
    )

    assert stored.object_bytes == len(transcription.data)
    assert stored.content_type == "audio/midi"
    assert stored.note_count == transcription.note_count
    assert stored.window_seconds == transcription.window_seconds
    assert stored.transcriber == transcription.name
    assert store.download(object_key=stored.object_key) == transcription.data


def test_storing_the_chords_writes_the_timeline_and_digests_it() -> None:
    """The digest and the payload come from one timeline, so a row cannot describe another."""
    store = FakeObjectStore()
    timeline = FakeChordTimeline()

    stored = artifacts.store_chords(store, user_id=new_id(), job_id=new_id(), timeline=timeline)

    assert stored.content_type == "application/json"
    assert stored.object_bytes == len(artifacts.encode_chords(timeline))
    assert stored.detector == timeline.name
    assert stored.vocabulary == timeline.vocabulary
    assert stored.segment_count == len(timeline.segments)
    assert stored.progression == ("Am",)
    assert stored.confidence == 0.9
    assert stored.no_chord_ratio == 0.0

    payload = json.loads(store.download(object_key=stored.object_key))
    assert payload["detector"] == timeline.name
    assert payload["key"] == timeline.key
    assert payload["hop_ms"] == timeline.hop_ms
    assert payload["segments"][0]["chord"] == "Am"


# --- The rows ----------------------------------------------------------------


def test_a_job_produces_bpm_key_chords_and_midi() -> None:
    """One row per artifact kind. Sections are not produced yet, and are not pretended into
    being."""
    results = _results()

    assert [result.kind for result in results] == ["bpm", "key", "chords", "midi"]


def test_every_inline_digest_fits_the_column() -> None:
    """``analysis_results_payload_bytes_check`` caps the digest at 8192 bytes.

    The chords digest is the one worth measuring: a progression and a handful of numbers, which have
    to stay a digest rather than growing with the length of the song.
    """
    for result in _results():
        assert result.payload_bytes <= MAX_SUMMARY_BYTES


def test_only_the_payload_rows_carry_an_object() -> None:
    """An artifact in the bucket without its size - or the other way round - is refused by
    ``analysis_results_object_check``, so the pair is asserted here too."""
    user_id, job_id = new_id(), new_id()
    store = FakeObjectStore()

    bpm, key, chords, midi = artifacts.build_results(
        analysis=FakeAnalysis(),
        midi=artifacts.store_midi(
            store,
            user_id=user_id,
            job_id=job_id,
            transcription=FakeTranscription(),
        ),
        chords=artifacts.store_chords(
            store,
            user_id=user_id,
            job_id=job_id,
            timeline=FakeChordTimeline(),
        ),
    )

    assert (bpm.object_key, bpm.object_bytes) == (None, None)
    assert (key.object_key, key.object_bytes) == (None, None)

    assert chords.object_key == artifacts.chords_object_key(user_id=user_id, job_id=job_id)
    assert chords.object_bytes == len(artifacts.encode_chords(FakeChordTimeline()))
    assert chords.object_content_type == "application/json"

    assert midi.object_key == artifacts.midi_object_key(user_id=user_id, job_id=job_id)
    assert midi.object_bytes == len(FakeTranscription().data)
    assert midi.object_content_type == "audio/midi"


def _results() -> list[ResultInput]:
    """The rows one succeeded job writes, from a fake analysis and a fake bucket."""
    user_id, job_id = new_id(), new_id()
    store = FakeObjectStore()

    return artifacts.build_results(
        analysis=FakeAnalysis(),
        midi=artifacts.store_midi(
            store,
            user_id=user_id,
            job_id=job_id,
            transcription=FakeTranscription(),
        ),
        chords=artifacts.store_chords(
            store,
            user_id=user_id,
            job_id=job_id,
            timeline=FakeChordTimeline(),
        ),
    )
