"""A recording's pitch-class energy, frame by frame - the reusable spectral pass.

Chroma is the one measurement both of this package's musical readers want: chords are decided
from it now, and a section detector will be decided from it later. So it lives on its own
rather than inside the chord detector that happens to be its first client.

Two registers come out of one decode. ``frames`` is the whole spectrum folded into twelve
pitch classes - the harmony. ``bass`` is the same fold restricted to C2-C4 - the register a
slash bass can actually come from, and the only thing that says whether a chord is an
inversion.

The cost is what makes this the right shape. ``chroma_cqt`` is linear in the length of the
recording and needs no model, so unlike the pitch tracker - about a second per second of audio
- it can run over the **whole** song, which is what makes a whole-song chord timeline
affordable at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from numpy.typing import NDArray

from app.workers.analysis import SAMPLE_RATE, load_samples

# ~93 ms per frame at 22.05 kHz: fine enough that a chord change lands where it happened,
# coarse enough that a four-minute song is a few thousand frames, not a hundred thousand.
HOP_LENGTH = 2048
HOP_MS = round(1000 * HOP_LENGTH / SAMPLE_RATE)

# The register a slash bass is read from: C2 to C4, which is where a bassist or a left hand
# plays. Above it is the harmony; below it is the kick drum.
BASS_LOWEST_NOTE = "C2"
BASS_OCTAVES = 2

# CQT bins per octave, and so how many bins that register spans. 36 is librosa's default
# resolution - three bins per semitone - and the same fold `chroma_cqt` uses.
BINS_PER_OCTAVE = 36
BASS_BINS = BASS_OCTAVES * BINS_PER_OCTAVE

# A silent frame has no direction, so normalizing it would divide by zero. This is the length
# every zero column is read at instead.
EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class ChromaFeatures:
    """One recording's harmony, its bass register, and where each frame sits in time.

    ``times_ms`` is the frame's own start, taken from librosa rather than computed here, so the
    hop is described by the library that applied it. ``duration_ms`` is the recording's real
    length, which is not the same as where the last frame starts - a chord held to the final bar
    ends at the end of the file, not at its last frame boundary.

    ``bass_bins`` is deliberately *not* folded into pitch classes the way ``frames`` is. A slash
    chord means "this note is underneath", and which note is underneath is a question about the
    lowest strong bin; folding the octaves together throws away exactly the octave that answers
    it.
    """

    frames: NDArray[np.float64]
    bass_bins: NDArray[np.float64]
    bass_frequencies: NDArray[np.float64]
    times_ms: NDArray[np.int64]
    duration_ms: int

    @property
    def frame_count(self) -> int:
        """How many frames the recording was measured in, at :data:`HOP_MS` apart."""
        return int(self.frames.shape[1])


def unit_columns(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Every column scaled to unit length, so a dot product against one is a cosine.

    Unit length and not a probability distribution: what a chord detector needs is the *shape*
    of a frame, and a cosine ignores how loud the frame was - a quiet verse and a loud chorus
    read as the same chord.
    """
    norms = np.linalg.norm(matrix, axis=0, keepdims=True)
    return matrix / np.maximum(norms, EPSILON)


def chroma_features(path: Path) -> ChromaFeatures:
    """Whole-recording chroma, at the analysis sample rate, tuned to the recording's own pitch.

    ``estimate_tuning`` is not a nicety: plenty of recordings sit a quarter-tone or so off
    concert pitch, and a detector that assumes A440 turns every one of them into a soup of
    wrong accidentals. The correction is measured from the recording itself and applied to both
    registers, so the bass and the harmony agree about what a note is.

    A decode failure is permanent and is raised as one, exactly as it is for every other reader
    of this file - these bytes will fail the same way on the next attempt.
    """
    samples, sample_rate = load_samples(path)
    duration_ms = round(len(samples) / sample_rate * 1000) if sample_rate else 0
    tuning = float(librosa.estimate_tuning(y=samples, sr=sample_rate))

    frames = librosa.feature.chroma_cqt(
        y=samples,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
        tuning=tuning,
    )
    bass = np.abs(
        librosa.cqt(
            y=samples,
            sr=sample_rate,
            hop_length=HOP_LENGTH,
            fmin=librosa.note_to_hz(BASS_LOWEST_NOTE),
            n_bins=BASS_BINS,
            bins_per_octave=BINS_PER_OCTAVE,
            tuning=tuning,
        )
    )

    seconds = librosa.times_like(frames, sr=sample_rate, hop_length=HOP_LENGTH)
    return ChromaFeatures(
        frames=unit_columns(np.asarray(frames, dtype=np.float64)),
        bass_bins=np.asarray(bass, dtype=np.float64),
        bass_frequencies=librosa.cqt_frequencies(
            n_bins=BASS_BINS,
            fmin=librosa.note_to_hz(BASS_LOWEST_NOTE),
            bins_per_octave=BINS_PER_OCTAVE,
        ),
        times_ms=(seconds * 1000).round().astype(np.int64),
        duration_ms=duration_ms,
    )
