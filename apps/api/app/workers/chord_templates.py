"""The chord vocabulary: which labels exist, and the chroma each one looks like.

Two things live here and nothing else. **Which chords this product can name** - a closed
grammar of ``(root, quality)`` pairs, spelled in the same twelve pitch-class names
``analysis.KEY_NAMES`` uses, so a key and a chord root are never two spellings of one pitch
class. And **what each of them looks like as a chroma vector**, which is the only thing a
detector can score a frame against.

The quality list is deliberately wider than what v1 confidently emits: a seventh or a sus is
*stored* when the detector is sure of it, and simplified to its parent triad when it is not
(:func:`parent_state`). Keeping the grammar wide now is what stops a later fretboard or
section feature from having to rewrite timelines that were already written to R2.

The weights are the whole of the musical knowledge in this module, and they say one thing:
the root is what a listener actually hears, and a seventh is the weakest evidence of the
four - which is why it is the first thing dropped when a frame is ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.workers.chord_summary import NO_CHORD

# The twelve spellings, in the order the chroma columns are laid out. Identical to
# `analysis.KEY_NAMES`, and shared vocabulary on purpose: a chord's root and a song's
# tonic are the same kind of name.
ROOT_NAMES = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# How much each interval of a chord counts as evidence. Root first, then the third, then
# the fifth-ish, then the seventh last: a chord is recognised by its root and its third
# before anything else about it.
INTERVAL_WEIGHTS: dict[int, float] = {
    0: 1.0,  # root
    4: 0.9,  # major third
    3: 0.9,  # minor third
    7: 0.8,  # perfect fifth
    6: 0.8,  # diminished fifth
    8: 0.8,  # augmented fifth
    2: 0.9,  # sus2
    5: 0.9,  # sus4
    11: 0.6,  # major seventh
    10: 0.6,  # minor seventh
}


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


# The grammar, in the order states are laid out. Every label the product can emit or
# store is one of these, with an optional "/<bass>" after it.
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

# One state per (root, quality), in that nesting order. The no-chord state is not one of
# these: it is appended after them by whoever scores a frame, because it has no template.
ROOTS = len(ROOT_NAMES)
STATE_COUNT = ROOTS * len(QUALITIES)

# The mode's own notes, as semitone offsets from the tonic, used to give a key's chords a
# small nudge over the ones it never contains.
MAJOR_DEGREES = (0, 2, 4, 5, 7, 9, 11)
MINOR_DEGREES = (0, 2, 3, 5, 7, 8, 10)

# How much more likely a chord is when it belongs to the detected key. Small on purpose:
# the key is evidence about the song, not a rule about it, and a strong prior would make
# the detector unable to report a borrowed chord.
DIATONIC_BONUS = 1.06


def _template(root: int, intervals: tuple[int, ...]) -> NDArray[np.float64]:
    """One chord as a unit-length chroma vector, rotated onto its own root.

    Unit length so that a dot product against a unit-length chroma column is the cosine - a
    similarity between 0 and 1 that does not care how loud the frame was. Rotated because the root
    is half of what a chord *is*: A minor and C major share two of their three notes, and only
    where those notes sit on the twelve decides which one was played.
    """
    vector = np.zeros(len(ROOT_NAMES), dtype=np.float64)
    for interval in intervals:
        vector[(root + interval) % len(ROOT_NAMES)] = INTERVAL_WEIGHTS[interval]
    return vector / float(np.linalg.norm(vector))


def _templates() -> NDArray[np.float64]:
    """Every state's template, as one ``(STATE_COUNT, 12)`` matrix, in state order.

    Built once, at import: the matrix is a constant in every sense except that numpy has to
    assemble it, and building it per frame would be the only real cost in scoring.

    The state index is ``root * len(QUALITIES) + quality``, spelled out here rather than called
    through :func:`root_of`, because this runs while the module is still being defined.
    """
    qualities = len(QUALITIES)
    return np.stack(
        [
            _template(index // qualities, QUALITIES[index % qualities].intervals)
            for index in range(STATE_COUNT)
        ]
    )


TEMPLATE_MATRIX = _templates()


def root_of(state: int) -> int:
    """The pitch class a state's chord is built on."""
    return state // len(QUALITIES)


def quality_of(state: int) -> Quality:
    """The quality of a state's chord."""
    return QUALITIES[state % len(QUALITIES)]


def label_of(state: int) -> str:
    """A state as the product spells it: ``Am``, ``F#m7b5``, ``C``."""
    return f"{ROOT_NAMES[root_of(state)]}{quality_of(state).suffix}"


def parent_state(state: int) -> int:
    """The same state's chord, without its extension.

    ``C:maj7`` becomes ``C``, ``A:m7`` becomes ``Am``, ``G:sus4`` becomes ``G``. A triad is
    returned unchanged, so this is safe to apply to any state.
    """
    return root_of(state) * len(QUALITIES) + QUALITY_INDEX[quality_of(state).parent]


def chord_tones(state: int) -> frozenset[int]:
    """The pitch classes a state's chord is made of.

    What a slash bass has to be one of: ``C/E`` describes a chord with an E in the bass, and
    ``C/F#`` describes nothing anyone played.
    """
    return frozenset(
        (root_of(state) + interval) % len(ROOT_NAMES) for interval in quality_of(state).intervals
    )


def diatonic_roots(key: str | None) -> frozenset[int]:
    """The pitch classes a key's own chords are built on, or none when there is no key.

    ``"A minor"`` is A, B, C, D, E, F and G. An unreadable key - ``None``, or a mode this
    module has never heard of - returns nothing rather than guessing, which leaves the
    detector exactly where it would have been without a key at all.
    """
    if not key:
        return frozenset()

    parts = key.split()
    if len(parts) != 2:
        return frozenset()

    tonic, mode = parts
    if tonic not in ROOT_NAMES:
        return frozenset()

    degrees = {"major": MAJOR_DEGREES, "minor": MINOR_DEGREES}.get(mode)
    if degrees is None:
        return frozenset()

    return frozenset((ROOT_NAMES.index(tonic) + degree) % len(ROOT_NAMES) for degree in degrees)


def states_for_key(key: str | None) -> tuple[frozenset[int], frozenset[int]]:
    """The chord states a key favours, and every other one: ``(diatonic, rest)``.

    Returned as indices into :data:`TEMPLATE_MATRIX`, so a caller applies the bonus with a slice
    rather than with a rule inside its scoring loop. A key nobody can read makes every state
    non-diatonic, which is the same as having no prior at all.
    """
    every = frozenset(range(STATE_COUNT))
    roots = diatonic_roots(key)
    if not roots:
        return frozenset(), every

    diatonic = frozenset(state for state in every if root_of(state) in roots)
    return diatonic, every - diatonic


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
