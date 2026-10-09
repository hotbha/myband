"""What the transcription writes, and what it says the melody was.

The audio is an arpeggio whose pitch classes are known before anything looks at it -
A, C and E, which is the A minor triad - so "did the template change" is answerable
without a golden file. What a *real* recording comes out as is a different question,
and one only a listener can answer: pYIN tracks the fundamental of whatever is
loudest, which is why docs/analysis-worker.md is explicit about this being a
monophonic sketch rather than a transcription of a mix.

Needs the audio stack; skips itself otherwise.
"""

import dataclasses
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import pytest

pytest.importorskip("librosa", reason="needs the worker dependency group")
pytest.importorskip("pretty_midi", reason="needs the worker dependency group")

import pretty_midi
from app.workers.midi import Transcription, render_midi, transcribe_with_pyin
from tests import audio
from tests.fakes import FakeTranscription

# The pitch classes the fixture plays: A, C and E.
TRIAD = {9, 0, 4}


@pytest.fixture(scope="module")
def melody(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A, C, E, twice over, one note at a time."""
    return audio.write_wav(
        tmp_path_factory.mktemp("midi") / "a-minor-melody.wav",
        audio.arpeggio([audio.A3, audio.C4, audio.E4], 0.5, repeats=2),
    )


@pytest.fixture(scope="module")
def transcription(melody: Path) -> Transcription:
    """One transcription, shared: pYIN costs about a second per second of audio."""
    return transcribe_with_pyin(melody, bpm=120.0, window_seconds=30)


def test_the_transcription_is_a_standard_midi_file(transcription: Transcription) -> None:
    """The bytes a DAW opens: an SMF header, one track, and the tempo it was given."""
    assert transcription.data[:4] == b"MThd"

    parsed = _parse(transcription.data)

    assert len(parsed.instruments) == 1
    assert transcription.note_count > 0
    assert transcription.note_count == len(parsed.instruments[0].notes)
    assert parsed.get_tempo_changes()[1][0] == pytest.approx(120.0, rel=0.01)
    assert transcription.name == "pyin-monophonic"


def test_the_notes_are_the_ones_that_were_played(transcription: Transcription) -> None:
    """Every note is from the triad, and all three of its pitch classes appear."""
    notes = _parse(transcription.data).instruments[0].notes

    assert {note.pitch % 12 for note in notes} == TRIAD


def test_the_notes_are_ordered_and_do_not_overlap(transcription: Transcription) -> None:
    """A monophonic line, which is what a DAW expects to be able to play back."""
    notes = _parse(transcription.data).instruments[0].notes

    for earlier, later in pairwise(notes):
        assert earlier.start <= later.start
        assert earlier.end <= later.start


def test_the_window_bounds_the_work(tmp_path: Path) -> None:
    """A long recording is only transcribed as far as the window asks.

    This is the whole reason the window exists: pYIN at full length would take most of
    an hour on a five minute song.
    """
    long_recording = audio.write_wav(
        tmp_path / "twelve-seconds.wav",
        audio.arpeggio([audio.A3, audio.C4, audio.E4], 0.5, repeats=8),
    )

    transcription = transcribe_with_pyin(long_recording, bpm=120.0, window_seconds=2)

    assert transcription.window_seconds == 2
    notes = _parse(transcription.data).instruments[0].notes
    assert notes, "two seconds of a melody should still produce notes"
    assert max(note.end for note in notes) <= 2.5


def test_silence_transcribes_to_a_valid_file_with_no_notes(tmp_path: Path) -> None:
    """Nothing to transcribe is not a failure: the tempo and key are already stored.

    A tempo-only file is more useful than a missing artifact - the row and the object
    still agree, and the count in the summary says zero. Reachable in production even
    though silence fails the analysis stage: a fade-in means a silent *window* on a
    file that does have a tempo.
    """
    transcription = transcribe_with_pyin(
        audio.write_wav(tmp_path / "silence.wav", audio.silence(2)),
        bpm=100.0,
        window_seconds=5,
    )

    assert transcription.note_count == 0
    assert transcription.data[:4] == b"MThd"
    # pretty_midi writes no track for an instrument with no notes, so the read-back is
    # empty rather than holding an empty instrument - the tempo survives either way.
    parsed = _parse(transcription.data)
    assert [note for instrument in parsed.instruments for note in instrument.notes] == []
    assert parsed.get_tempo_changes()[1][0] == pytest.approx(100.0)


def test_render_midi_writes_the_notes_it_is_given() -> None:
    """The writer, on its own: no audio, no detector, just the file format."""
    parsed = _parse(render_midi([(0.0, 0.5, 60), (0.5, 1.0, 64)], bpm=100.0))

    assert [note.pitch for note in parsed.instruments[0].notes] == [60, 64]
    assert parsed.get_tempo_changes()[1][0] == pytest.approx(100.0)


def _parse(data: bytes) -> pretty_midi.PrettyMIDI:
    """Read the bytes back the way a DAW would, so the assertion is about the file."""
    return pretty_midi.PrettyMIDI(BytesIO(data))


def test_the_pipeline_tests_use_the_same_shape_as_this_dataclass() -> None:
    """The scripted transcriber in ``tests/fakes.py`` mirrors :class:`Transcription`.

    Mirrors it rather than importing it, because the pipeline's tests must run without the
    audio stack installed - which is only safe while the two agree.
    """
    assert [field.name for field in dataclasses.fields(Transcription)] == [
        field.name for field in dataclasses.fields(FakeTranscription)
    ]
