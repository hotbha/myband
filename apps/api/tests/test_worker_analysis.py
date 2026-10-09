"""What the detectors say about recordings whose answers are known in advance.

These are the tests that would catch a detector quietly becoming wrong - a chroma
profile mixed up with its rotations, a tempo estimate halved - which is the failure
mode that matters for this product and that no amount of database testing would see.

Needs the audio stack (``uv sync --project apps/api --group worker``); skips itself
otherwise, the same way the database suites skip themselves without a database URL.
"""

import dataclasses
from pathlib import Path

import pytest

pytest.importorskip("librosa", reason="needs the worker dependency group")

from app.workers.analysis import (
    AudioAnalysis,
    analyze,
    detect_key,
    detect_tempo,
    load_samples,
    read_duration_ms,
)
from app.workers.errors import FailureCode, PermanentError
from tests import audio
from tests.fakes import FakeAnalysis


@pytest.fixture(scope="module")
def recordings(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One recording per question, built once for the whole module.

    Module scoped because each analysis is seconds of work: cheap, but not free, and
    nothing here writes to a file another test reads.
    """
    directory = tmp_path_factory.mktemp("analysis")

    return {
        # A 120 BPM pulse with an A minor arpeggio over it: the "song" case, where both
        # answers are known.
        "song": audio.write_wav(
            directory / "song-in-a-minor.wav",
            audio.mix(
                audio.metronome(120, 8),
                audio.arpeggio([audio.A3, audio.C4, audio.E4, audio.A4], 0.5, repeats=4),
            ),
        ),
        "metronome": audio.write_wav(directory / "metronome-120.wav", audio.metronome(120, 8)),
        "a_minor": audio.write_wav(
            directory / "a-minor.wav",
            audio.arpeggio([audio.A3, audio.C4, audio.E4, audio.A4], 0.5, repeats=4),
        ),
        "c_major": audio.write_wav(
            directory / "c-major.wav",
            audio.arpeggio([audio.C4_LOW, audio.E4, audio.G4, audio.C5], 0.5, repeats=4),
        ),
        "silence": audio.write_wav(directory / "silence.wav", audio.silence(2)),
        "not_audio": _write_text(directory / "notes.txt"),
    }


def _samples(recordings: dict[str, Path], name: str) -> tuple[object, int]:
    """The decoded samples of one recording, for a single-detector test."""
    return load_samples(recordings[name])


def test_duration_comes_from_the_file_header(recordings: dict[str, Path]) -> None:
    """Eight seconds of audio is eight thousand milliseconds, to the sample."""
    assert read_duration_ms(recordings["metronome"]) == 8000


def test_the_tempo_of_a_click_track(recordings: dict[str, Path]) -> None:
    """A click every half second is 120 BPM, and the tracker should say so."""
    bpm, beats = detect_tempo(*_samples(recordings, "metronome"))

    assert bpm == pytest.approx(120.0, rel=0.05)
    assert beats >= 14  # sixteen beats exist; missing one or two is tolerable


def test_a_song_reports_its_tempo_and_its_key(recordings: dict[str, Path]) -> None:
    """The headline case: a pulse and a key in the same file, both recovered."""
    analysis = analyze(recordings["song"])

    assert analysis.duration_ms == 8000
    assert analysis.bpm == pytest.approx(120.0, rel=0.08)
    assert analysis.musical_key == "A minor"
    assert analysis.key_strength > 0.6


def test_an_a_minor_arpeggio_is_a_minor(recordings: dict[str, Path]) -> None:
    """A3, C4, E4, A4 is the A minor triad and nothing else."""
    musical_key, strength = detect_key(*_samples(recordings, "a_minor"))

    assert musical_key == "A minor"
    assert strength > 0.6


def test_a_c_major_arpeggio_is_c_major(recordings: dict[str, Path]) -> None:
    """The other mode from a different tonic: the profiles are not favouring one."""
    musical_key, _ = detect_key(*_samples(recordings, "c_major"))

    assert musical_key == "C major"


def test_silence_is_refused_rather_than_guessed(recordings: dict[str, Path]) -> None:
    """Silence has no tempo, and storing one anyway is how a library fills with lies."""
    with pytest.raises(PermanentError) as raised:
        analyze(recordings["silence"])

    assert raised.value.code is FailureCode.UNANALYZABLE
    assert raised.value.retryable is False


def test_a_file_that_is_not_audio_is_a_decode_error(recordings: dict[str, Path]) -> None:
    """The other permanent failure, and a different one: the file cannot be read."""
    with pytest.raises(PermanentError) as raised:
        analyze(recordings["not_audio"])

    assert raised.value.code is FailureCode.DECODE_ERROR


def test_a_missing_recording_is_a_decode_error(tmp_path: Path) -> None:
    with pytest.raises(PermanentError) as raised:
        analyze(tmp_path / "not-there.wav")

    assert raised.value.code is FailureCode.DECODE_ERROR


def _write_text(path: Path) -> Path:
    """Something with the right name and none of the right bytes."""
    path.write_text("this is not a recording\n", encoding="utf-8")
    return path


def test_the_pipeline_tests_use_the_same_shape_as_this_dataclass() -> None:
    """The scripted analyzer in ``tests/fakes.py`` mirrors :class:`AudioAnalysis`.

    Mirrors it rather than importing it, because the pipeline's tests must run without the
    audio stack installed - which is only safe while the two agree. This is the assertion
    that makes them disagree loudly instead of silently.
    """
    assert [field.name for field in dataclasses.fields(AudioAnalysis)] == [
        field.name for field in dataclasses.fields(FakeAnalysis)
    ]
