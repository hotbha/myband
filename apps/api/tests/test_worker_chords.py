"""What the recording plays, read back from audio whose answer was decided in advance.

The fixtures are synthesized triads: A minor is A, C and E sounding *together*, at a known time, in
a known order. That makes "did the detector find the right chord" a question about the detector
rather than about a track somebody had an opinion about - the same trick ``test_worker_analysis.py``
uses for tempo and key.

Needs the audio stack; skips itself otherwise.
"""

import dataclasses
from itertools import pairwise
from pathlib import Path

import pytest

pytest.importorskip("librosa", reason="needs the worker dependency group")

from app.workers import chord_summary, chord_templates, chords
from app.workers.chord_summary import NO_CHORD
from app.workers.chords import ChordSegment, ChordTimeline, detect_chords
from tests import audio
from tests.fakes import FakeChordSegment, FakeChordTimeline

# Four triads, sounded together rather than in sequence.
A_MINOR = [audio.A3, audio.C4, audio.E4]
F_MAJOR = [audio.F3, audio.A3, audio.C4]
C_MAJOR = [audio.C4_LOW, audio.E4, audio.G4]
G_MAJOR = [audio.G3, audio.B3, audio.D4]

LOOP = [A_MINOR, F_MAJOR, C_MAJOR, G_MAJOR]
PLAYED = ["Am", "F", "C", "G"] * 2
SECONDS_EACH = 1.0
LOOP_MS = int(len(PLAYED) * SECONDS_EACH * 1000)


@pytest.fixture(scope="module")
def loop(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The four chords, one after another, twice over."""
    return audio.write_wav(
        tmp_path_factory.mktemp("chords") / "a-minor-loop.wav",
        audio.progression(LOOP * 2, SECONDS_EACH),
    )


@pytest.fixture(scope="module")
def timeline(loop: Path) -> ChordTimeline:
    """One detection, shared: decoding a whole recording is this module's expensive part."""
    return detect_chords(loop, key="A minor")


# --- The chords that were played ----------------------------------------------


def test_the_loop_comes_back_as_its_four_chords(timeline: ChordTimeline) -> None:
    """Every chord in the loop is found, and nothing that was not played is invented."""
    assert set(chord_summary.progression(timeline.segments)) == {"Am", "F", "C", "G"}
    assert timeline.key == "A minor"
    assert timeline.name == "librosa-chroma-viterbi"
    assert timeline.vocabulary == "1.0"
    assert chord_summary.silence_ratio(timeline.segments) == 0.0


def test_each_chord_lands_where_it_was_played(timeline: ChordTimeline) -> None:
    """Eight chords of one second each, in order, each starting within a frame or two of its bar.

    Frame-accurate and not beat-snapped, which is the v1 decision: a few frames of slop at a
    boundary is honest, and a confidently wrong downbeat would not be.
    """
    assert [segment.chord for segment in timeline.segments] == PLAYED

    for index, segment in enumerate(timeline.segments):
        assert segment.start_ms == pytest.approx(index * SECONDS_EACH * 1000, abs=200)
        assert segment.confidence > 0.8


def test_the_timeline_covers_the_recording_without_gaps_or_overlaps(
    timeline: ChordTimeline,
) -> None:
    """One chord ends exactly where the next begins, and the last ends at the end of the file."""
    assert timeline.segments[0].start_ms == 0
    assert timeline.segments[-1].end_ms == LOOP_MS

    for earlier, later in pairwise(timeline.segments):
        assert earlier.start_ms < earlier.end_ms
        assert earlier.end_ms == later.start_ms


def test_the_same_recording_always_produces_the_same_timeline(loop: Path) -> None:
    """Determinism, asserted rather than assumed: nothing here may depend on a random seed."""
    first = detect_chords(loop, key="A minor")
    second = detect_chords(loop, key="A minor")

    assert first.segments == second.segments


def test_a_held_chord_is_one_segment_and_not_a_hundred_guesses(tmp_path: Path) -> None:
    """What the Viterbi pass is for: a steady chord is one segment with one label."""
    timeline = detect_chords(
        audio.write_wav(tmp_path / "a-minor.wav", audio.chord(A_MINOR, 3.0)),
        key="A minor",
    )

    assert [segment.chord for segment in timeline.segments] == ["Am"]


# --- The note underneath ------------------------------------------------------


def test_an_inversion_is_reported_with_the_note_underneath_it(tmp_path: Path) -> None:
    """A C major triad over a low E is C/E, not C: the bass is half of what a voicing says."""
    timeline = detect_chords(
        audio.write_wav(
            tmp_path / "c-over-e.wav",
            audio.chord([audio.E2, audio.C4_LOW, audio.E4, audio.G4], 2.0),
        ),
        key="C major",
    )

    assert [segment.chord for segment in timeline.segments] == ["C/E"]


def test_a_chord_whose_root_is_in_the_bass_takes_no_slash(tmp_path: Path) -> None:
    """The ordinary case, and the one a slash detector gets wrong: F over an F3 is still just F.

    The bass is the *lowest* note in the register, not the loudest - a triad states its root at the
    bottom far more often than it states anything else.
    """
    timeline = detect_chords(
        audio.write_wav(tmp_path / "f-major.wav", audio.chord(F_MAJOR, 2.0)),
        key="F major",
    )

    assert [segment.chord for segment in timeline.segments] == ["F"]


# --- Silence, and chords nobody is sure of ------------------------------------


def test_silence_is_no_chord_rather_than_a_guess(tmp_path: Path) -> None:
    """A recording with nothing tonal in it reports no-chord for its whole length, and says so.

    Not a failure: the tempo, key and MIDI were still produced, and a timeline that claims a chord
    nobody played is worse than one that admits there is nothing there.
    """
    timeline = detect_chords(
        audio.write_wav(tmp_path / "silence.wav", audio.silence(2)),
        key="A minor",
    )

    assert [segment.chord for segment in timeline.segments] == [NO_CHORD]
    assert chord_summary.silence_ratio(timeline.segments) == 1.0
    assert chord_summary.progression(timeline.segments) == ()
    assert chord_summary.confidence(timeline.segments) == 0.0


def test_no_segment_claims_an_extension_it_is_not_sure_of(timeline: ChordTimeline) -> None:
    """The rule the vocabulary is built around, as an invariant over real detections.

    A speculative seventh loses to a certain triad: a segment that stored an extension, an inversion
    or a slash bass was sure enough of it to say so, which is the same rule
    ``chord_summary.simplify_label`` applies, and it is checked here against a recording rather than
    against a table of examples.
    """
    for segment in timeline.segments:
        if segment.chord == NO_CHORD:
            continue

        root, _, bass = segment.chord.partition("/")
        if bass:
            assert segment.confidence >= chords.SLASH_CONFIDENCE
        if chord_summary.simplify_label(root) != root:
            assert segment.confidence >= chords.EXTENSION_CONFIDENCE


# --- The vocabulary -----------------------------------------------------------


def test_the_grammar_simplifies_every_extension_to_its_triad() -> None:
    """The rule the vocabulary is built around, as a table: a speculative seventh loses to a triad.

    Fmaj7 is F, Am7 is Am, Gsus4 is G, Bm7b5 is Bdim - and a slash bass goes with the extension,
    because a segment that is not sure of its seventh is not sure of its inversion either.
    """
    assert chord_summary.simplify_label("Fmaj7") == "F"
    assert chord_summary.simplify_label("Am7") == "Am"
    assert chord_summary.simplify_label("Gsus4") == "G"
    assert chord_summary.simplify_label("Dsus2") == "D"
    assert chord_summary.simplify_label("Bm7b5") == "Bdim"
    assert chord_summary.simplify_label("G7") == "G"
    assert chord_summary.simplify_label("C/E") == "C"
    # A triad is left exactly as it was, and so is a label this vocabulary does not know.
    assert chord_summary.simplify_label("F#m") == "F#m"
    assert chord_summary.simplify_label("C") == "C"
    assert chord_summary.simplify_label("Hmaj9") == "Hmaj9"
    assert chord_summary.simplify_label(NO_CHORD) == NO_CHORD


def test_the_grammar_is_the_ten_qualities_over_the_twelve_roots() -> None:
    """The closed set of names the product can emit, store, and read back later."""
    assert [quality.suffix for quality in chord_templates.QUALITIES] == [
        "",
        "m",
        "dim",
        "aug",
        "sus2",
        "sus4",
        "maj7",
        "m7",
        "7",
        "m7b5",
    ]
    qualities = len(chord_templates.QUALITIES)
    roots = len(chord_templates.ROOT_NAMES)
    assert qualities * roots == chord_templates.STATE_COUNT

    labels = {chord_templates.label_of(state) for state in range(chord_templates.STATE_COUNT)}
    assert {"A", "Am", "G7", "Fmaj7", "Csus4", "Bm7b5", "F#dim"} <= labels


def test_the_key_is_a_bias_and_never_a_rule() -> None:
    """``"A minor"`` is A B C D E F G. A key nobody can read biases nothing at all."""
    assert chord_templates.diatonic_roots("A minor") == frozenset({9, 11, 0, 2, 4, 5, 7})
    assert chord_templates.diatonic_roots("C major") == frozenset({0, 2, 4, 5, 7, 9, 11})
    assert chord_templates.diatonic_roots("A dorian") == frozenset()
    assert chord_templates.diatonic_roots("H minor") == frozenset()
    assert chord_templates.diatonic_roots(None) == frozenset()

    diatonic, rest = chord_templates.states_for_key("A dorian")
    assert diatonic == frozenset()
    assert len(rest) == chord_templates.STATE_COUNT


# --- The digest ---------------------------------------------------------------


def test_the_digest_describes_the_segments_it_was_given() -> None:
    """The numbers a row holds, from four segments and nothing else - no detector involved."""
    segments = (
        ChordSegment(start_ms=0, end_ms=1000, chord=NO_CHORD, confidence=0.1),
        ChordSegment(start_ms=1000, end_ms=4000, chord="Am", confidence=0.9),
        ChordSegment(start_ms=4000, end_ms=6000, chord="G", confidence=0.8),
        ChordSegment(start_ms=6000, end_ms=8000, chord="Am", confidence=0.7),
    )

    assert chord_summary.segment_count(segments) == 4
    assert chord_summary.duration_ms(segments) == 8000
    # Duration-weighted, so the two Am segments together outrank G.
    assert chord_summary.progression(segments) == ("Am", "G")
    # The no-chord segment is not one of the chords, so it is not part of the mean.
    assert chord_summary.confidence(segments) == pytest.approx(0.8)
    assert chord_summary.silence_ratio(segments) == 0.125


def test_an_empty_timeline_digests_to_nothing_rather_than_to_zero() -> None:
    """What a timeline with no segments at all reports, so that nothing divides by zero."""
    assert chord_summary.duration_ms(()) == 0
    assert chord_summary.progression(()) == ()
    assert chord_summary.confidence(()) == 0.0
    assert chord_summary.silence_ratio(()) == 0.0


def test_coverage_measures_a_card_against_the_recording_it_describes() -> None:
    """How much of the song the chords on a card account for, silence included in the denominator.

    The number a chord screen puts beside "these are the chords this song is made of": four fifths
    of this recording is the two chords, and the fifth that is silence is not something a card can
    claim. A chord left off the card is held time too, and is simply not counted towards it.
    """
    segments = (
        ChordSegment(start_ms=0, end_ms=2000, chord="Am", confidence=0.9),
        ChordSegment(start_ms=2000, end_ms=3000, chord="G", confidence=0.8),
        ChordSegment(start_ms=3000, end_ms=5000, chord=NO_CHORD, confidence=0.2),
    )

    assert chord_summary.coverage(segments, ("Am", "G")) == 0.6
    # A shorter ranking than the card's own claims less, rather than ceasing to be measurable.
    assert chord_summary.coverage(segments, ("Am",)) == 0.4
    # A rest is not a chord however a ranking spells it, and an empty one claims nothing at all.
    assert chord_summary.coverage(segments, (NO_CHORD,)) == 0.0
    assert chord_summary.coverage(segments, ()) == 0.0
    assert chord_summary.coverage((), ("Am",)) == 0.0


def test_the_pipeline_tests_use_the_same_shapes_as_these_dataclasses() -> None:
    """``tests/fakes.py`` mirrors :class:`ChordTimeline` and :class:`ChordSegment`.

    Mirrors them rather than importing them, because the pipeline's tests must run without the audio
    stack installed - which is only safe while the two agree. This is the assertion that makes them
    disagree loudly instead of silently.
    """
    assert [field.name for field in dataclasses.fields(ChordTimeline)] == [
        field.name for field in dataclasses.fields(FakeChordTimeline)
    ]
    assert [field.name for field in dataclasses.fields(ChordSegment)] == [
        field.name for field in dataclasses.fields(FakeChordSegment)
    ]
