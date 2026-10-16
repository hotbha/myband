"""Reading a section list back: how a song's shape reads, and what is worth counting.

The **form** is the thing here. A section list in time order already says everything the
worker measured, but nobody reads eight timings to notice that a song is ``A B A B C`` -
and that string is what makes a stored section list a *map* rather than a table.

Three more numbers, and all three are deliberately cheap: how many sections there are,
where the last one ends, and how tightly the detector's own blocks agreed with the section
they were put in. The last one is not on the same scale as a chord's confidence -
:class:`app.workers.sections.Section` says why - so it is a relative figure: it compares one
section of one song with another, not a section with a chord.

It is a module of its own for the reason :mod:`app.workers.chord_summary` is: section
*detection* needs librosa, while writing the row that describes the result does not, and
:mod:`app.workers.artifacts` sits on the wrong side of that line to be importing an audio
stack in order to count sections.

Everything here takes a sequence of sections and reads four attributes off each one, so it
works on the detector's own sections and on a test's stand-in without either knowing about
the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class Section(Protocol):
    """The four things anything section-shaped has to have for this module to read it."""

    start_ms: int
    end_ms: int
    label: str
    confidence: float


def section_count(sections: Iterable[Section]) -> int:
    """How many sections the list holds."""
    return len(list(sections))


def duration_ms(sections: Iterable[Section]) -> int:
    """Where the last section ends, or ``0`` for an empty list.

    The same read :func:`app.workers.chord_summary.duration_ms` makes over a timeline, and
    for the same reason: it is the one number that says the sections reach the end of the
    recording rather than stopping somewhere inside it.
    """
    ordered = list(sections)
    return 0 if not ordered else ordered[-1].end_ms


def labels(sections: Iterable[Section]) -> tuple[str, ...]:
    """The distinct labels, in the order the recording first uses them.

    ``A`` is always the opening, because that is how the detector names them - so this is
    the vocabulary the form is written in, and nothing more.
    """
    seen: dict[str, None] = {}
    for section in sections:
        seen.setdefault(section.label, None)

    return tuple(seen)


def form(sections: Iterable[Section]) -> str:
    """The shape of the song as one line: ``A B A B C``, repeats and all.

    Every section, in time order, by label. Not a ranking like a chord progression and not
    deduplicated: a form that dropped the repeats would describe the sections a song has
    instead of the order it plays them in, and the order is the whole point.
    """
    return " ".join(section.label for section in sections)


def confidence(sections: Iterable[Section]) -> float:
    """The mean confidence of the sections, or ``0.0`` for an empty list.

    Read rather than recomputed anywhere else: a second mean would be a second definition
    of it, the same rule the chord digest's confidence follows.
    """
    ordered = list(sections)
    if not ordered:
        return 0.0

    return round(sum(section.confidence for section in ordered) / len(ordered), 3)
