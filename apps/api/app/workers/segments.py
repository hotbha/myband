"""Turning per-frame scores into labelled spans of time.

Three problems, and both musical readers in this package have them. A decoder has to turn
per-frame scores into a *sequence* of states, or a held chord comes out as a hundred alternating
guesses. Then that sequence has to survive a single misread frame. Then spans too short to be
anything have to be absorbed into their neighbours. Chord detection hits all three today; section
detection will next, over exactly this kind of score matrix.

So the mechanics live here, with no opinion about what a label *means*. A score matrix is
``(states, frames)`` and a path is a sequence of integer state ids; everything below is arithmetic
on those two, which is why this module knows nothing about chroma, chords or audio.

Kept deterministic on purpose: a tie is broken by the lowest state id, never by chance, because
two runs over the same recording have to produce the same timeline.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

# One run of frames: `(first frame, last frame + 1, state)`.
Run = tuple[int, int, int]


def viterbi(emissions: NDArray[np.float64], self_transition: float) -> NDArray[np.int64]:
    """The most likely *sequence* of states, given per-frame log-emissions.

    Sequence and not frame: every frame is decided with the whole recording behind it, which is
    what stops a held chord from being reported as twenty alternating guesses. Staying is
    ``self_transition`` likely and every change is equally unlikely, which is the smallest
    transition model that produces held labels.
    """
    states, frames = emissions.shape
    if frames == 0:
        return np.zeros(0, dtype=np.int64)

    move = math.log((1.0 - self_transition) / (states - 1))
    stay = math.log(self_transition)
    # `transitions[from, to]`, transposed so a row reads "where this state came from".
    transitions = np.where(np.eye(states, dtype=bool), stay, move).T

    pointers = np.zeros((frames, states), dtype=np.int64)
    best = emissions[:, 0].copy()
    for index in range(1, frames):
        # One row per state: what it costs to be here, having come from each state before it.
        candidates = best[np.newaxis, :] + transitions
        pointers[index] = np.argmax(candidates, axis=1)
        best = emissions[:, index] + candidates[np.arange(states), pointers[index]]

    path = np.zeros(frames, dtype=np.int64)
    path[-1] = int(np.argmax(best))
    for index in range(frames - 1, 0, -1):
        path[index - 1] = pointers[index, path[index]]
    return path


def runs(path: NDArray[np.int64]) -> list[Run]:
    """The path as the runs it is made of, in order.

    Half-open on purpose - ``end`` is the frame *after* the run - so a run's width is ``end -
    start`` and two runs that meet share one boundary rather than one frame.
    """
    if path.size == 0:
        return []

    edges = np.flatnonzero(path[1:] != path[:-1]) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [path.size]])
    return [
        (int(start), int(end), int(path[start])) for start, end in zip(starts, ends, strict=True)
    ]


def majority(path: NDArray[np.int64], window: int) -> NDArray[np.int64]:
    """A majority vote over a window of frames, so one misread frame is not a change.

    A vote rather than a median because a state id is a *name*, not a number: the median of C
    and F# is not a chord, and taking one would invent a label nobody played.
    """
    half = window // 2
    smoothed = path.copy()
    for index in range(path.size):
        nearby = path[max(0, index - half) : index + half + 1]
        values, counts = np.unique(nearby, return_counts=True)
        smoothed[index] = values[int(np.argmax(counts))]
    return smoothed


def trim(decoded: list[Run], times_ms: NDArray[np.int64], minimum_ms: int) -> list[Run]:
    """Absorb runs too short to be anything into the neighbour they sit against.

    Absorbed into a *boundary*, never into a label: the short run's frames join the span beside
    it, whose confidence then describes the frames it really covers. A first run that is too
    short extends the one after it backwards instead, so a timeline starts at zero.
    """
    kept: list[Run] = []
    pending: int | None = None

    for start, end, state in decoded:
        if pending is not None:
            start, pending = pending, None

        if times_ms[end - 1] - times_ms[start] >= minimum_ms:
            kept.append((start, end, state))
        elif kept:
            previous_start, _, previous_state = kept[-1]
            kept[-1] = (previous_start, end, previous_state)
        else:
            pending = start

    if not kept and decoded:
        # Every run was shorter than a chord. Report the longest one, covering all of them: a
        # recording that plainly had frames deserves a timeline rather than an empty one.
        longest = max(decoded, key=lambda run: run[1] - run[0])
        kept = [(decoded[0][0], decoded[-1][1], longest[2])]

    return kept
