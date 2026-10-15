"""What the recording plays, chord by chord, across the whole song.

This is the third thing an analysis produces, beside the headline numbers and the MIDI
sketch, and it is the one that answers a musical question rather than a numerical one: not
"how fast" but "what is happening in bar 9".

**How it works, in four steps, all of them named algorithms.**

1. **Chroma.** :func:`app.workers.chroma.chroma_features` folds the recording's spectrum into
   twelve pitch-class energies per frame, over the *whole* track. It is the cheap detector, so
   the whole track is affordable here in a way it never is for the pitch tracker - and it lives
   in a module of its own because a section detector will want exactly those frames.
2. **Scoring.** Every frame is scored against every chord in the vocabulary
   (:mod:`app.workers.chord_templates`) by cosine similarity, and the key the analysis
   already found nudges that key's own chords slightly ahead of the rest.
3. **Decoding.** A Viterbi pass picks the most likely *sequence* of labels, not the best
   label per frame, with an explicit no-chord state and a strong preference for staying put.
   That is what stops a held chord from being reported as twenty alternating guesses, and
   what makes silence honestly silent rather than some chord nobody played.
4. **Simplification.** A segment's confidence is the mean similarity behind it. Below
   :data:`EXTENSION_CONFIDENCE` an extension is reported as its parent triad - `Fmaj7` as
   `F`, `Am7` as `Am`, `Gsus4` as `G` - because a speculative seventh is a worse answer than
   a certain triad, and below :data:`NO_CHORD_CONFIDENCE` the segment is no chord at all.

**Why not from the MIDI.** The only symbolic artifact this pipeline produces is a
monophonic sketch of the opening - at most the first two minutes of it - and it follows the
bass: on the recording this was checked against, every note it wrote in the window sat in
C2-C3. Harmony is a fact about notes sounding *together*, and there is no reliable way to
recover it from a monophonic line of the intro. The chords are therefore read from the audio,
which is where they are.

**Beat and bar snapping is deliberately off in v1.** Segments are frame-accurate. Snapping
would put a wrong downbeat on every segment instead of a slightly ragged right one, and
nothing downstream needs bars yet - if sections do, the grid it will want is the one
``analysis.detect_tempo`` already computes.

Nothing here touches a connection, a clock or the queue: a path in, a
:class:`ChordTimeline` out, which is what lets it be tested against synthesized triads with a
known answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from numpy.typing import NDArray

from app.workers import chord_templates as templates
from app.workers import segments
from app.workers.chord_summary import NO_CHORD
from app.workers.chroma import HOP_MS, ChromaFeatures, chroma_features

# How a stored timeline says who made it, and under which grammar. Both travel into the row's
# digest, because a re-run under a new detector must not look like a disagreement.
DETECTOR_NAME = "librosa-chroma-viterbi"
VOCABULARY_VERSION = "1.0"

# Majority vote over this many frames, before segments are cut. A chord change is not
# instantaneous in a real recording, and without this every transition becomes a one-frame
# segment labelled something nobody played.
SMOOTHING_FRAMES = 5

# Nothing shorter than this is a chord change; it is a wobble, and it is absorbed into its
# neighbourhood. Half a second is well under the shortest chord anyone writes.
MIN_SEGMENT_MS = 500

# How willing the sequence is to move, and how much one frame of evidence counts against moving.
# Staying is much more likely than changing, which is what turns a frame-by-frame argmax into held
# chords - but on its own it is *too* sticky, because a cosine similarity is a narrow scale: the
# best and worst chord for a frame differ by well under two nats, while changing state in a
# 121-state model costs more than six. `EVIDENCE_PER_FRAME` is what rebalances the two, and it is
# the one number here that was tuned against real audio rather than derived.
SELF_TRANSITION = 0.8
EVIDENCE_PER_FRAME = 15.0

# Below this, an extension is reported as its parent triad; below `NO_CHORD_CONFIDENCE`, the
# segment is no chord at all. Both are judgements about a cosine similarity, and both are
# deliberately low: this detector would rather say "C" than "Cmaj7", and rather say "N" than a
# chord it cannot hear.
EXTENSION_CONFIDENCE = 0.70
NO_CHORD_CONFIDENCE = 0.30

# A slash bass has to be this clear before an inversion is claimed, and this far above the floor
# of the register before it counts as the lowest note at all.
SLASH_CONFIDENCE = 0.55
BASS_PROMINENCE = 0.5

# A similarity of zero has no logarithm. This is the floor it is read at instead.
EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class ChordSegment:
    """One chord, held for a stretch of the recording.

    The same four fields a *section* will have - a start, an end, a label and how sure the
    detector is - so one renderer and one shared schema can serve both.
    """

    start_ms: int
    end_ms: int
    chord: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ChordTimeline:
    """Every chord a recording plays, in order, and what made them.

    ``key`` is the key the analysis measured, passed in so the decoder could use it and kept so a
    stored timeline explains itself. ``name`` and ``vocabulary`` are provenance: they say which
    detector produced this and under which grammar, which is what makes a stored timeline readable
    after either changes.

    What a timeline *summarises to* - its progression, its mean confidence, how much of it was
    silence - belongs to :mod:`app.workers.chord_summary` rather than to this type, so the storage
    layer can read a timeline back without importing an audio stack.
    """

    segments: tuple[ChordSegment, ...]
    key: str | None
    name: str = DETECTOR_NAME
    vocabulary: str = VOCABULARY_VERSION
    hop_ms: int = HOP_MS


def _similarity(frames: NDArray[np.float64]) -> NDArray[np.float64]:
    """How much every state looks like every frame: ``(STATE_COUNT + 1, frame count)``.

    The chord states are one matrix multiply - the templates are unit length and so are the
    frames, so the product *is* the cosine. The last row is the no-chord state, and it is the
    complement of the best chord rather than a template of its own: a frame that looks like no
    chord is exactly a frame that looks like nothing else.
    """
    scored = templates.TEMPLATE_MATRIX @ frames
    silence = np.maximum(1.0 - scored.max(axis=0), EPSILON)
    return np.vstack([scored, silence[np.newaxis, :]])


def _emissions(similarity: NDArray[np.float64], key: str | None) -> NDArray[np.float64]:
    """The similarity matrix as log-emissions, with the key's own chords nudged ahead.

    The nudge is applied here, to the emissions, and deliberately *not* to the similarity the
    caller reads back: a prior is a reason to prefer a chord, not evidence that it was played,
    and inflating the reported confidence with it would make the digest lie.
    """
    weighted = similarity.copy()
    diatonic, _ = templates.states_for_key(key)
    if diatonic:
        weighted[sorted(diatonic)] *= templates.DIATONIC_BONUS
    return np.log(np.maximum(weighted, EPSILON)) * EVIDENCE_PER_FRAME


def _bass(features: ChromaFeatures, start: int, end: int) -> int | None:
    """The lowest pitch class with real energy in the bass register, or ``None``.

    Lowest rather than loudest: a slash chord is a statement about voicing - which note is
    *underneath* - and in a triad the root is not reliably the loudest thing in the low end.
    """
    if features.bass_bins.shape[1] == 0:
        return None

    energy = features.bass_bins[:, start:end].mean(axis=1)
    peak = float(energy.max())
    if peak <= 0.0:
        return None

    strong = np.flatnonzero(energy >= BASS_PROMINENCE * peak)
    if strong.size == 0:
        return None

    hertz = float(features.bass_frequencies[int(strong[0])])
    note = float(librosa.hz_to_midi(hertz))
    return round(note) % len(templates.ROOT_NAMES)


def _label(features: ChromaFeatures, run: segments.Run, confidence: float) -> str:
    """What one run is called, once its confidence has had its say."""
    start, end, state = run

    if state == templates.STATE_COUNT or confidence < NO_CHORD_CONFIDENCE:
        return NO_CHORD

    if confidence < EXTENSION_CONFIDENCE:
        # An extension nobody is sure of is reported as the triad underneath it: Fmaj7 is F.
        state = templates.parent_state(state)

    bass = _bass(features, start, end)
    if (
        bass is not None
        and confidence >= SLASH_CONFIDENCE
        and bass != templates.root_of(state)
        and bass in templates.chord_tones(state)
    ):
        return f"{templates.label_of(state)}/{templates.ROOT_NAMES[bass]}"

    return templates.label_of(state)


def _segments(
    features: ChromaFeatures,
    path: NDArray[np.int64],
    similarity: NDArray[np.float64],
) -> tuple[ChordSegment, ...]:
    """The decoded path as chord segments, in real time.

    A segment ends where the next one starts, and the last one ends at the end of the file rather
    than at its final frame boundary - a chord held to the last bar is held to the last bar.
    """
    times = features.times_ms
    confidence_of_frame = similarity[path, np.arange(path.size)]

    found: list[ChordSegment] = []
    for run in segments.trim(segments.runs(path), times, MIN_SEGMENT_MS):
        starts_at = int(times[run[0]])
        ends_at = features.duration_ms if run[1] >= path.size else int(times[run[1]])
        if ends_at <= starts_at:
            ends_at = starts_at + HOP_MS

        confidence = round(float(np.mean(confidence_of_frame[run[0] : run[1]])), 3)
        found.append(
            ChordSegment(
                start_ms=starts_at,
                end_ms=ends_at,
                chord=_label(features, run, confidence),
                confidence=confidence,
            )
        )

    return tuple(found)


def detect_chords(path: Path, *, key: str | None = None) -> ChordTimeline:
    """Every chord the recording at ``path`` plays, in order.

    ``key`` is the key the analysis already measured. It is passed in rather than re-derived: the
    analysis measured it over the whole recording with a published algorithm, and the decoder
    only wants it as a mild preference (:func:`_emissions`).

    A recording with nothing tonal in it is not an error. It comes back as one no-chord segment
    covering the whole track, and the digest says so - silence is a fact about a recording, not a
    failure to analyse one.
    """
    features = chroma_features(path)
    if features.frame_count == 0:
        if features.duration_ms <= 0:
            return ChordTimeline(segments=(), key=key)
        silence = (
            ChordSegment(start_ms=0, end_ms=features.duration_ms, chord=NO_CHORD, confidence=0.0),
        )
        return ChordTimeline(segments=silence, key=key)

    similarity = _similarity(features.frames)
    scores = segments.viterbi(_emissions(similarity, key), SELF_TRANSITION)
    decoded = segments.majority(scores, SMOOTHING_FRAMES)
    return ChordTimeline(segments=_segments(features, decoded, similarity), key=key)

    return path
