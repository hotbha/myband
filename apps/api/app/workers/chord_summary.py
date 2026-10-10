"""Reading a chord timeline back: how to spell a chord, and what is worth summarising.

Three things, all dependency-free on purpose.

``NO_CHORD`` is the label for "nothing was played here" - not a chord with no extension, the
absence of one - and it lives here because the detector, this digest and the API all have to spell
it the same way.

The grammar's **names**: which suffixes exist, what each of them degrades to when a frame is not
clear enough to justify its extension, and :func:`simplify_label`, which turns one of those names
into the triad it is really describing. They live here rather than in
:mod:`app.workers.chord_templates` for the same reason the digest does - the API serves a *simple*
view of a stored timeline, and it cannot import a module that assembles a chroma matrix with numpy
in order to do it. ``chord_templates`` imports them back, so the grammar is still stated exactly
once, and the chroma the detector scores against stays next to the weights that decide it.

And the **digest**: how many segments a timeline has, how long they run, how sure the detector was,
how much of the recording was silent, which chords the song is *made of*, and how much of the
recording those chords account for.

It is a module of its own because of who needs it. Chord *detection* needs librosa; writing the row
that describes the result does not, and :mod:`app.workers.artifacts` sits on the wrong side of that
line to be importing an audio stack in order to count segments.

Everything here takes a sequence of segments and reads four attributes off each one, so it works on
the detector's own segments and on a test's stand-in without either of them knowing about the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

# The label for "nothing is being played here". Spelled outside the chord grammar, and never
# simplified into one.
NO_CHORD = "N"

# How many chords the digest's progression lists. Enough to describe a song, small enough that the
# inline summary stays a digest.
PROGRESSION_LIMIT = 6


@dataclass(frozen=True, slots=True)
class Quality:
    """One chord quality: its suffix, its intervals, and the triad it degrades to.

    ``parent`` is the suffix of the simpler chord this one becomes when a frame is not
    clear enough to justify the extension - ``maj7`` to ``""`` (Fmaj7 becomes F), ``m7``
    to ``"m"`` (Am7 becomes Am), ``sus4`` to ``""`` (Gsus4 becomes G). A quality that is
    already a triad is its own parent, so an ``aug`` is never quietly renamed.
    """

    suffix: str
    intervals: tuple[int, ...]
    parent: str


# The grammar, in the order states are laid out. Every label the product can emit or store is
# one of these, with an optional "/<bass>" after it, and it is deliberately wider than what v1
# confidently emits: a seventh or a sus is *stored* when the detector is sure of it, and
# simplified to its parent triad when it is not - keeping the grammar wide now is what stops a
# later feature from having to rewrite timelines that were already written to R2.
QUALITIES: tuple[Quality, ...] = (
    Quality("", (0, 4, 7), ""),
    Quality("m", (0, 3, 7), "m"),
    Quality("dim", (0, 3, 6), "dim"),
    Quality("aug", (0, 4, 8), "aug"),
    Quality("sus2", (0, 2, 7), ""),
    Quality("sus4", (0, 5, 7), ""),
    Quality("maj7", (0, 4, 7, 11), ""),
    Quality("m7", (0, 3, 7, 10), "m"),
    Quality("7", (0, 4, 7, 10), ""),
    Quality("m7b5", (0, 3, 6, 10), "dim"),
)

QUALITY_INDEX: dict[str, int] = {quality.suffix: index for index, quality in enumerate(QUALITIES)}


def simplify_label(label: str) -> str:
    """A label without its extension or its inversion.

    ``Fmaj7`` is ``F``, ``Am7`` is ``Am``, ``Gsus4`` is ``G``, ``C/E`` is ``C``, and ``N`` is
    left alone - it is not a chord with an extension, it is the absence of one. Anything
    unreadable is returned as it came: a label this function does not understand is a label it
    has no business rewriting.
    """
    if label == NO_CHORD:
        return label

    root, _, bass = label.partition("/")
    # Longest suffix first, so `m7b5` is tried before `m7` before `m`.
    for quality in sorted(QUALITIES, key=lambda item: -len(item.suffix)):
        if quality.suffix and root.endswith(quality.suffix):
            return f"{root[: -len(quality.suffix)]}{quality.parent}"

    return root if bass else label


class Segment(Protocol):
    """The four things anything segment-shaped has to have for this module to read it."""

    start_ms: int
    end_ms: int
    chord: str
    confidence: float


def segment_count(segments: Iterable[Segment]) -> int:
    """How many segments the timeline holds."""
    return len(list(segments))


def duration_ms(segments: Iterable[Segment]) -> int:
    """Where the last segment ends, or ``0`` for an empty timeline."""
    ordered = list(segments)
    return 0 if not ordered else ordered[-1].end_ms


def confidence(segments: Iterable[Segment]) -> float:
    """The mean confidence of the segments that named a chord.

    No-chord segments are left out: how sure the detector is that a passage is silent is a different
    question from how sure it is about the chords, and mixing them would let a long quiet intro make
    the whole analysis look uncertain.
    """
    named = [segment.confidence for segment in segments if segment.chord != NO_CHORD]
    if not named:
        return 0.0
    return round(sum(named) / len(named), 3)


def silence_ratio(segments: Iterable[Segment]) -> float:
    """How much of the recording had no chord in it, between 0 and 1.

    Reported rather than hidden: a timeline that is mostly no-chord is telling the truth about a
    sparse or percussive recording, and a reader who could not see that would read the chords it
    *did* find as covering the whole song.
    """
    ordered = list(segments)
    total = duration_ms(ordered)
    if not ordered or not total:
        return 0.0

    quiet = sum(
        segment.end_ms - segment.start_ms for segment in ordered if segment.chord == NO_CHORD
    )
    return round(quiet / total, 3)


def progression(
    segments: Iterable[Segment],
    *,
    limit: int = PROGRESSION_LIMIT,
) -> tuple[str, ...]:
    """The chords a song is *made of*, longest total time first.

    Ordered by how much of the song each chord occupies rather than by when it first appears,
    because that is the ordering that describes the song: a chorus chord held for a minute is what
    it is about, and the passing chord in bar 2 is not. No-chord stretches are not chords at all.
    """
    held: dict[str, int] = {}
    for segment in segments:
        if segment.chord == NO_CHORD:
            continue
        held[segment.chord] = held.get(segment.chord, 0) + (segment.end_ms - segment.start_ms)

    ranked = sorted(held.items(), key=lambda item: (-item[1], item[0]))
    return tuple(chord for chord, _ in ranked[:limit])


def coverage(segments: Iterable[Segment], labels: Iterable[str]) -> float:
    """How much of the recording the given chords account for, between 0 and 1.

    What a card of "these are the chords this song is made of" claims, and the one number that can
    contradict it: the same six chords accounting for 92% of a recording is a description of it,
    and accounting for 59% is a list of its landmarks. The denominator is the recording rather than
    the time that had a chord in it - the timeline describes the whole song, and a reader who
    compares this with :func:`silence_ratio` should see one pie and not two.

    ``labels`` is a ranking - the card's own, in the order it shows them - and not a statement
    about what was played: a chord it leaves out is held time this does not count towards it, and a
    stretch with no chord in it is never counted as one the card accounts for, however spelled.
    """
    wanted = frozenset(labels)
    ordered = list(segments)
    total = duration_ms(ordered)
    if not ordered or not total or not wanted:
        return 0.0

    named = sum(
        segment.end_ms - segment.start_ms
        for segment in ordered
        if segment.chord != NO_CHORD and segment.chord in wanted
    )
    return round(named / total, 3)
