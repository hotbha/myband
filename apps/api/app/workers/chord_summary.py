"""Reading a chord timeline back: how to spell it, and what is worth summarising.

Two things, both dependency-free on purpose.

``NO_CHORD`` is the label for "nothing was played here" - not a chord with no extension, the
absence of one - and it lives here because the detector, this digest and the API all have to spell
it the same way.

And the digest: how many segments a timeline has, how long they run, how sure the detector was, how
much of the recording was silent, and which chords the song is *made of*.

It is a module of its own because of who needs it. Chord *detection* needs librosa; writing the row
that describes the result does not, and :mod:`app.workers.artifacts` sits on the wrong side of that
line to be importing an audio stack in order to count segments.

Everything here takes a sequence of segments and reads four attributes off each one, so it works on
the detector's own segments and on a test's stand-in without either of them knowing about the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

# The label for "nothing is being played here". Spelled outside the chord grammar, and never
# simplified into one.
NO_CHORD = "N"

# How many chords the digest's progression lists. Enough to describe a song, small enough that the
# inline summary stays a digest.
PROGRESSION_LIMIT = 6


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
