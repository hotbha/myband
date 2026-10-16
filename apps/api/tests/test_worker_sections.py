"""The shape of a song, read back from audio whose shape was decided in advance.

The fixture is three sixteen-second stretches - A, B, A - whose harmony was written before the
detector looked at it: two chords alternating in A minor and F, then two in C and G, then the
first pair again. That makes "did it find the repeat" a question about the detector rather than
about a track somebody had an opinion about, the same trick ``test_worker_chords.py`` uses for
the chords themselves.

**What is not asserted here is a name.** A section detector cannot know that a stretch is a
chorus; it knows that two stretches are the same music, and that is what these tests hold it to.
The letters are a vocabulary, not a claim about the arrangement.

Needs the audio stack; skips itself otherwise.
"""

import dataclasses
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

pytest.importorskip("librosa", reason="needs the worker dependency group")

from app.workers import section_summary, sections
from app.workers.sections import Section, SectionTimeline, detect_sections
from tests import audio
from tests.fakes import FakeSection, FakeSectionTimeline

A_MINOR = [audio.A3, audio.C4, audio.E4]
F_MAJOR = [audio.F3, audio.A3, audio.C4]
C_MAJOR = [audio.C4_LOW, audio.E4, audio.G4]
G_MAJOR = [audio.G3, audio.B3, audio.D4]

# Two chords to a section, each held for two seconds, four times over: sixteen seconds of one
# kind of music, which is what a verse or a chorus is as far as this detector can tell.
SECONDS_EACH = 2.0
STRETCHES = 4
STRETCH_MS = int(SECONDS_EACH * 2 * STRETCHES * 1000)
SRC = [A_MINOR, F_MAJOR]
OTHER = [C_MAJOR, G_MAJOR]


def _stretch(pairs: list[list[float]]) -> NDArray[np.float32]:
    """One section's worth of audio: the two chords, alternating, over and over."""
    return audio.progression(pairs * STRETCHES, SECONDS_EACH)


@pytest.fixture(scope="module")
def aba(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A, B, A: the smallest recording that has a form worth reporting."""
    return audio.write_wav(
        tmp_path_factory.mktemp("sections") / "aba.wav",
        np.concatenate([_stretch(SRC), _stretch(OTHER), _stretch(SRC)]),
    )


@pytest.fixture(scope="module")
def timeline(aba: Path) -> SectionTimeline:
    """One detection, shared: reading a whole recording is this module's expensive part."""
    return detect_sections(aba)


# --- The form that was played -------------------------------------------------


def test_the_repeat_comes_back_as_a_repeat(timeline: SectionTimeline) -> None:
    """A B A, and not three sections with three names: the repeat is what a form is for."""
    assert [section.label for section in timeline.sections] == ["A", "B", "A"]
    assert section_summary.form(timeline.sections) == "A B A"
    assert section_summary.labels(timeline.sections) == ("A", "B")


def test_each_section_lands_where_it_was_played(timeline: SectionTimeline) -> None:
    """Three stretches of sixteen seconds, each starting within one block of its own bar.

    Boundaries land on the 4-second pool rather than on a frame, which is the resolution this
    detector has and the one ``hop_ms`` reports. An approximate start that admits its grid is
    worth more than a precise one nobody can reproduce.
    """
    assert [section.start_ms for section in timeline.sections] == pytest.approx(
        [0, STRETCH_MS, STRETCH_MS * 2], abs=sections.POOL_MS
    )


def test_the_sections_cover_the_recording_without_gaps_or_overlaps(
    timeline: SectionTimeline,
) -> None:
    """One section ends exactly where the next begins, and the last ends at the end of the file."""
    assert timeline.sections[0].start_ms == 0
    assert timeline.sections[-1].end_ms == STRETCH_MS * 3

    for earlier, later in pairwise(timeline.sections):
        assert earlier.start_ms < earlier.end_ms
        assert earlier.end_ms == later.start_ms


def test_the_timeline_says_which_detector_made_it(timeline: SectionTimeline) -> None:
    """Provenance, and the grid - which is the pool, not the chroma frame."""
    assert timeline.name == "chroma-pool-cluster-viterbi"
    assert timeline.vocabulary == "1.0"
    assert timeline.hop_ms == sections.POOL_MS
    assert timeline.hop_ms == 4000


def test_the_same_recording_always_produces_the_same_sections(aba: Path) -> None:
    """Determinism, asserted rather than assumed: nothing here may depend on a random seed."""
    first = detect_sections(aba)
    second = detect_sections(aba)

    assert first.sections == second.sections


def test_a_section_may_hold_several_chords(tmp_path: Path) -> None:
    """Sixteen seconds of Am and F alternating is one section, not eight.

    This is the whole difference between this detector and the chord reader next door: the pool
    is two bars wide, so a progression that repeats inside a section reads as one stretch of
    music rather than as its chords.
    """
    timeline = detect_sections(audio.write_wav(tmp_path / "loop.wav", _stretch(SRC)))

    assert [section.label for section in timeline.sections] == ["A"]
    assert timeline.sections[0].start_ms == 0
    assert timeline.sections[0].end_ms == STRETCH_MS


# --- Recordings with nothing to tell apart ------------------------------------


def test_silence_has_no_sections_to_find(tmp_path: Path) -> None:
    """A recording with nothing in it reports no sections rather than one called A.

    A form is a claim that a stretch *recurs*, and there is nothing to recur in silence. The
    tempo, key and MIDI were still measured; this artifact says there is nothing here.
    """
    timeline = detect_sections(audio.write_wav(tmp_path / "silence.wav", audio.silence(20.0)))

    assert timeline.sections == ()
    assert section_summary.form(timeline.sections) == ""
    assert section_summary.section_count(timeline.sections) == 0


def test_a_recording_shorter_than_one_block_is_one_section(tmp_path: Path) -> None:
    """Three seconds of music has a shape - all of it - and one section is that shape."""
    timeline = detect_sections(audio.write_wav(tmp_path / "short.wav", audio.chord(A_MINOR, 2.0)))

    assert [section.label for section in timeline.sections] == ["A"]
    assert timeline.sections[0].start_ms == 0
    assert timeline.sections[0].end_ms == pytest.approx(2000, abs=100)


# --- The digest ---------------------------------------------------------------


def test_the_digest_describes_the_sections_it_was_given() -> None:
    """The numbers a row holds, from four sections and nothing else - no detector involved."""
    shape = (
        Section(start_ms=0, end_ms=4000, label="A", confidence=0.9),
        Section(start_ms=4000, end_ms=8000, label="B", confidence=0.6),
        Section(start_ms=8000, end_ms=12000, label="A", confidence=0.8),
        Section(start_ms=12000, end_ms=16000, label="C", confidence=0.7),
    )

    assert section_summary.section_count(shape) == 4
    assert section_summary.duration_ms(shape) == 16000
    # The form keeps the repeats and the order they came in: that is the whole point of it.
    assert section_summary.form(shape) == "A B A C"
    # The vocabulary is first-appearance order, which is what makes A the opening.
    assert section_summary.labels(shape) == ("A", "B", "C")
    assert section_summary.confidence(shape) == pytest.approx(0.75)


def test_an_empty_list_digests_to_nothing_rather_than_to_zero() -> None:
    """What a recording with no sections reports, so that nothing divides by zero."""
    assert section_summary.section_count(()) == 0
    assert section_summary.duration_ms(()) == 0
    assert section_summary.form(()) == ""
    assert section_summary.labels(()) == ()
    assert section_summary.confidence(()) == 0.0


def test_the_pipeline_tests_use_the_same_shapes_as_these_dataclasses() -> None:
    """``tests/fakes.py`` mirrors :class:`SectionTimeline` and :class:`Section`.

    Mirrors them rather than importing them, because the pipeline's tests must run without the
    audio stack installed - which is only safe while the two agree. This is the assertion that
    makes them disagree loudly instead of silently.
    """
    assert [field.name for field in dataclasses.fields(SectionTimeline)] == [
        field.name for field in dataclasses.fields(FakeSectionTimeline)
    ]
    assert [field.name for field in dataclasses.fields(Section)] == [
        field.name for field in dataclasses.fields(FakeSection)
    ]
