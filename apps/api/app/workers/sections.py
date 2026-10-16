"""The shape of the song: which stretches are the same piece of music, and in what order.

This is the fifth thing an analysis produces, and the one that answers a question about the
*song* rather than about a moment in it: not "what chord is this" but "how is this built".

**How it works, in four steps, all of them named algorithms.**

1. **Pooling.** The chroma frames are averaged into blocks of :data:`POOL_MS` - two bars at
   a walking tempo - and each block is read as one harmony. Sections live at that scale, so
   a comparison made frame by frame would be reading chords, and one made over the whole
   recording would be reading the song.
2. **Clustering.** The blocks are sorted into :data:`SECTION_STATES` groups by k-means over
   cosine distance, from an initial guess spread evenly across the recording rather than
   drawn at random. That is what makes two runs over one file agree.
3. **Decoding.** :mod:`app.workers.segments` does the rest, unchanged from the way chord
   detection uses it: a Viterbi pass picks the most likely *sequence* of groups, a majority
   vote absorbs a single block read wrongly, and spans too short to be a section are
   absorbed into their neighbour.
4. **Labelling.** Each group is named after the first place it appears - ``A`` for the
   opening, ``B`` for the next new thing, and so on - so a repeat is visible as a repeat.

**Why letters and not verse and chorus.** The names a musician would use come from the
lyrics and the arrangement: a chorus is the part with the hook, and a hook is words and a
melody, neither of which this detector reads. Renaming a cluster "verse" would be a guess
dressed as a fact, and a wrong one on every song whose second section is a bridge. The
letter claims exactly what was measured - this stretch is the same music as that one - and
the form ``A B A B C`` is the map that claim was always about.

**Nothing here touches a connection, a clock or the queue**: a path in, a
:class:`SectionTimeline` out, which is what lets it be tested against a recording whose
shape was decided in advance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.workers import segments
from app.workers.chroma import HOP_MS, ChromaFeatures, chroma_features, unit_columns

# How a stored section list says who made it, and under which grammar. Both travel into the
# row's digest, because a re-run under a new detector must not look like a disagreement.
DETECTOR_NAME = "chroma-pool-cluster-viterbi"
VOCABULARY_VERSION = "1.0"

# The window a section is judged over, and so the grid its boundaries land on: two bars at a
# walking tempo. Shorter than this and the detector is reading chords; longer and a whole
# verse is one block, which nothing can be told apart in.
POOL_MS = 4000
POOL_FRAMES = max(1, round(POOL_MS / HOP_MS))

# How many kinds of section the detector may name. A ceiling rather than a setting: a song
# with two section types uses two, and the spare groups stay empty.
SECTION_STATES = 6

# Lloyd's algorithm, from the initial guess to convergence. Bounded rather than open-ended
# because a detector has a budget, and it converges within a handful of passes on anything
# with structure in it.
CLUSTER_ITERATIONS = 25
CLUSTER_TOLERANCE = 1e-6

# How willing the sequence is to move, and how much one block of evidence counts against
# moving - the same rebalancing chord detection needs, for the same reason: a cosine is a
# narrow scale, and log-emissions over it are what a transition cost has to be weighed in.
SELF_TRANSITION = 0.8
EVIDENCE_PER_FRAME = 15.0

# A majority vote over this many blocks, so one block of a verse that happens to sound like
# the chorus does not cut the verse in three.
SMOOTHING_BLOCKS = 3

# Nothing shorter than this is a section. Well under the shortest section anyone writes -
# eight seconds is two bars of a slow song - and comfortably over one block, so a single
# block can never be reported as a section of its own.
MIN_SECTION_MS = 8000

# A similarity of zero has no logarithm. This is the floor it is read at instead.
EPSILON = 1e-9

# What the groups are called, in the order they are discovered. There are only ever
# `SECTION_STATES` of them, so the alphabet is a ceiling rather than a limit.
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class Section:
    """One stretch of the song, held for a while, and the label it shares with its repeats.

    ``label`` is the letter of the group this stretch was decoded into, so two sections that
    are the same music carry the same letter.

    ``confidence`` is how tightly this section's blocks agreed with the group they were put
    in, in 0..1 - and it is *not* the same measurement as a chord's confidence. A group is
    the mean of the blocks that make it up, so agreement is high by construction and a
    section is never reported at 0.4 the way a chord can be. It compares one section of a
    song with another section of the same song, which is what makes it worth showing at all.
    """

    start_ms: int
    end_ms: int
    label: str
    confidence: float


@dataclass(frozen=True, slots=True)
class SectionTimeline:
    """Every section a recording is built from, in order, and what made them.

    ``name`` and ``vocabulary`` are provenance, exactly as they are on a chord timeline: they
    say which detector produced this and under which grammar, which is what makes a stored
    list readable after either changes.

    ``hop_ms`` is the *pool*, not the chroma frame: it is the grid the boundaries actually
    land on, and reporting the frame hop would promise an accuracy this detector does not
    have.

    What a timeline *summarises to* - its form, its mean confidence - belongs to
    :mod:`app.workers.section_summary` rather than to this type, so the storage layer can
    read a section list back without importing an audio stack.
    """

    sections: tuple[Section, ...]
    name: str = DETECTOR_NAME
    vocabulary: str = VOCABULARY_VERSION
    hop_ms: int = POOL_MS


def _pooled(features: ChromaFeatures) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """The recording's harmony one block at a time, and where each block starts.

    A block is the mean of the frames under it, re-normalized, so it is compared as a cosine
    like every other frame in this package. Blocks are whole: a partial one at the end is
    dropped rather than averaged over less music than the others, and the section it belonged
    to still ends at the end of the file.

    A recording shorter than one block is one block. It has a shape - all of it - and
    answering "no sections" to a three-second file would be a worse answer than "one".
    """
    frames = features.frames
    blocks = features.frame_count // POOL_FRAMES
    if blocks == 0:
        if features.frame_count == 0:
            return np.zeros((frames.shape[0], 0), dtype=np.float64), np.zeros(0, dtype=np.int64)
        return unit_columns(frames.mean(axis=1, keepdims=True)), np.zeros(1, dtype=np.int64)

    whole = frames[:, : blocks * POOL_FRAMES]
    pooled = whole.reshape(frames.shape[0], blocks, POOL_FRAMES).mean(axis=2)
    starts = features.times_ms[np.arange(blocks) * POOL_FRAMES]
    return unit_columns(pooled), starts


def _centres(pooled: NDArray[np.float64], states: int) -> NDArray[np.float64]:
    """``states`` kinds of section, as the mean harmony of the blocks that look most alike.

    Lloyd's algorithm over cosine similarity, from an initial guess spread across the
    recording instead of drawn at random: a detector whose answer depended on a seed could
    not be compared with itself, and there is nothing a random start buys here that an even
    one does not. A group with nothing in it keeps the guess it started with, so the number
    of groups is decided once, by :data:`SECTION_STATES`, and never by an empty cluster.
    """
    blocks = pooled.shape[1]
    states = min(states, blocks)
    centres = pooled[:, np.linspace(0, blocks - 1, states).round().astype(np.int64)].copy()

    for _ in range(CLUSTER_ITERATIONS):
        assigned = np.argmax(centres.T @ pooled, axis=0)
        updated = centres.copy()
        for state in range(states):
            members = pooled[:, assigned == state]
            if members.shape[1]:
                updated[:, state] = members.mean(axis=1)

        updated = unit_columns(updated)
        if np.allclose(updated, centres, atol=CLUSTER_TOLERANCE):
            break
        centres = updated

    return centres


def _decoded(similarity: NDArray[np.float64]) -> NDArray[np.int64]:
    """One group per block: the most likely *sequence*, not the best block-by-block guess.

    A single block skips the Viterbi pass rather than running it over one state, which would
    divide by the transitions there are none of. One block is one answer.
    """
    if similarity.shape[1] == 1:
        return np.zeros(1, dtype=np.int64)

    emissions = np.log(np.maximum(similarity, EPSILON)) * EVIDENCE_PER_FRAME
    return segments.majority(segments.viterbi(emissions, SELF_TRANSITION), SMOOTHING_BLOCKS)


def _sections(
    features: ChromaFeatures,
    pooled: NDArray[np.float64],
    starts: NDArray[np.int64],
    decoded: NDArray[np.int64],
    scores: NDArray[np.float64],
) -> tuple[Section, ...]:
    """The decoded blocks as sections, in real time, each named after the first of its kind.

    A section ends where the next one starts, and the last one ends at the end of the file
    rather than at its final block - a chorus held to the last bar is held to the last bar.

    The letters are handed out in this pass, in order of first appearance, because that is
    the only way to know that the *opening* section is ``A``: the group index a cluster
    happens to have says nothing about where in the song it is heard first.
    """
    found: list[Section] = []
    letters: dict[int, str] = {}

    for start, end, state in segments.trim(segments.runs(decoded), starts, MIN_SECTION_MS):
        starts_at = int(starts[start])
        ends_at = features.duration_ms if end >= pooled.shape[1] else int(starts[end])
        if ends_at <= starts_at:
            ends_at = starts_at + POOL_MS

        letters.setdefault(state, LETTERS[len(letters)])
        found.append(
            Section(
                start_ms=starts_at,
                end_ms=ends_at,
                label=letters[state],
                confidence=round(float(np.mean(scores[start:end])), 3),
            )
        )

    return tuple(found)


def detect_sections(path: Path) -> SectionTimeline:
    """Which stretches of the recording at ``path`` are the same music, in order.

    A recording with nothing tonal in it comes back as an empty list rather than as one
    section called ``A``: a form is a claim that a stretch recurs, and there is nothing to
    recur in silence. That is the section-shaped version of the no-chord segment, and the
    digest carries the same answer - no sections, no form.
    """
    features = chroma_features(path)
    pooled, starts = _pooled(features)
    if pooled.shape[1] == 0 or not np.any(pooled):
        return SectionTimeline(sections=())

    similarity = _centres(pooled, SECTION_STATES).T @ pooled
    decoded = _decoded(similarity)
    scores = similarity[decoded, np.arange(decoded.size)]

    return SectionTimeline(sections=_sections(features, pooled, starts, decoded, scores))
