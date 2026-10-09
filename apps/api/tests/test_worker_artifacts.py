"""The shapes one analysis leaves behind: no bucket, no database, no audio.

What is asserted here is the vocabulary a stored result uses - which kinds exist, where
the MIDI goes, what the inline digests say - because that vocabulary is a contract with
the UI and with every stored row. The MIDI's key shape is checked against a copy of
``analysis_results_object_key_check`` on purpose: the migration is the authority, and this
is the test that fails when the code and the CHECK drift apart.
"""

import re

from app.core.ids import new_id
from app.models.analysis_result import MAX_SUMMARY_BYTES, ResultInput
from app.workers import artifacts
from tests.fakes import FakeAnalysis, FakeObjectStore, FakeTranscription

OBJECT_KEY_PATTERN = re.compile(r"^users/[0-9a-fA-F-]{36}/[A-Za-z0-9._/-]+$")


def test_the_midi_key_names_the_owner_the_job_and_the_file() -> None:
    user_id, job_id = new_id(), new_id()

    key = artifacts.midi_object_key(user_id=user_id, job_id=job_id)

    assert key == f"users/{user_id}/analysis/{job_id}/transcription.mid"
    assert OBJECT_KEY_PATTERN.fullmatch(key) is not None
    assert len(key) <= 512  # `analysis_results_object_key_check`, second half


def test_the_key_is_stable_for_one_job_and_different_between_jobs() -> None:
    """Idempotency starts here: a second run writes over the first run's object."""
    user_id, job_id = new_id(), new_id()

    assert artifacts.midi_object_key(user_id=user_id, job_id=job_id) == artifacts.midi_object_key(
        user_id=user_id, job_id=job_id
    )
    assert artifacts.midi_object_key(user_id=user_id, job_id=job_id) != artifacts.midi_object_key(
        user_id=user_id, job_id=new_id()
    )


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


def test_a_v1_job_produces_three_kinds_of_artifact() -> None:
    """Tempo, key and MIDI. Chords and sections are not pretended into existence."""
    results = _results()

    assert [result.kind for result in results] == ["bpm", "key", "midi"]


def test_every_inline_digest_fits_the_column() -> None:
    """``analysis_results_payload_bytes_check`` caps the digest at 8192 bytes."""
    for result in _results():
        assert result.payload_bytes <= MAX_SUMMARY_BYTES


def test_only_the_midi_row_carries_an_object() -> None:
    """An artifact in the bucket without its size - or the other way round - is refused
    by ``analysis_results_object_check``, so the pair is asserted here too."""
    bpm, key, midi = _results()

    assert (bpm.object_key, bpm.object_bytes) == (None, None)
    assert (key.object_key, key.object_bytes) == (None, None)
    assert midi.object_key is not None
    assert midi.object_bytes == len(FakeTranscription().data)
    assert midi.object_content_type == "audio/midi"


def _results() -> list[ResultInput]:
    """The rows one succeeded job writes, from a fake analysis and a fake bucket."""
    store = FakeObjectStore()
    stored = artifacts.store_midi(
        store,
        user_id=new_id(),
        job_id=new_id(),
        transcription=FakeTranscription(),
    )
    return artifacts.build_results(analysis=FakeAnalysis(), stored=stored)
