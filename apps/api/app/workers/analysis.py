"""What a recording says about itself: how long it is, its tempo, and its key.

The engine is librosa, and every answer is a named algorithm rather than something
invented here:

* **duration** comes from the file's own header (``soundfile``), so it is exact,
  costs no decoding, and is right for MP3 and WAV alike.
* **tempo** comes from `librosa.beat.beat_track`, dynamic-programming beat tracking
  over an onset envelope. The number of beats found is reported alongside it, so a
  reviewer can see whether the tracker agreed with itself.
* **key** comes from Krumhansl-Schmuckler: the recording's average chroma is
  correlated against the 24 key profiles (major and minor, from every tonic) and the
  best match wins. The winning correlation is reported as the key's strength, which
  is what turns "A minor" into a claim that can be judged rather than a label that
  has to be taken on faith.

**Not essentia**, and not by preference: `essentia` publishes no Windows build at
all, and its current release only ships a ``cp314`` wheel, so it cannot be installed
for this project's Python 3.12 (docs/analysis-worker.md). The seam that would take
it is :func:`analyze` itself - the return value is the whole contract - and the
Krumhansl-Schmuckler profiles below are the reference implementation that essentia's
EDMA profiles are an improvement on.

Nothing in this module touches a connection, the clock or the queue: a path in, an
:class:`AudioAnalysis` out. That is what lets the pipeline above it be tested without
audio, and this be tested without a database.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from app.workers.errors import FailureCode, PermanentError

# The analysis sample rate. 22.05 kHz keeps every pitch and beat this product reports
# (the lowest note it claims is C2, 65 Hz) while halving the work of 44.1 kHz.
SAMPLE_RATE = 22050

# "A minor" and friends: the 24 spellings, in the order chroma columns are laid out.
KEY_NAMES = (
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

# Krumhansl-Schmuckler key profiles: how strongly each of the twelve pitch classes
# is heard in a major (or minor) key, measured from listener judgements. Rotation
# picks the tonic.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
KEY_PROFILES: dict[str, NDArray[np.float64]] = {"major": MAJOR_PROFILE, "minor": MINOR_PROFILE}


@dataclass(frozen=True, slots=True)
class AudioAnalysis:
    """The headline of one recording, in the terms the product shows it.

    ``duration_ms`` is an integer because that is what ``songs.duration_ms`` holds;
    ``bpm`` stays a float because rounding it to whole beats is a presentation
    decision, not a measurement one.
    """

    duration_ms: int
    bpm: float
    musical_key: str
    key_strength: float
    beats: int


def analyze(path: Path) -> AudioAnalysis:
    """Duration, tempo and key for the recording at ``path``.

    Raises :class:`PermanentError` when the file cannot be read or holds nothing
    measurable - the two cases where another attempt would be wasted work.
    """
    duration_ms = read_duration_ms(path)
    samples, sample_rate = load_samples(path)

    bpm, beats = detect_tempo(samples, sample_rate)
    musical_key, strength = detect_key(samples, sample_rate)

    return AudioAnalysis(
        duration_ms=duration_ms,
        bpm=bpm,
        musical_key=musical_key,
        key_strength=strength,
        beats=beats,
    )


def read_duration_ms(path: Path) -> int:
    """How long the recording is, in whole milliseconds, from its header.

    Read from the container rather than from decoded samples, so it costs nothing
    and cannot disagree with what a player would report.
    """
    try:
        info = sf.info(str(path))
    except (sf.LibsndfileError, OSError) as error:
        raise PermanentError(
            FailureCode.DECODE_ERROR, f"cannot read {path.name}: {error}"
        ) from error

    if info.frames <= 0 or info.samplerate <= 0:
        raise PermanentError(FailureCode.DECODE_ERROR, f"{path.name} holds no audio")

    return round(info.frames / info.samplerate * 1000)


def detect_tempo(samples: NDArray[np.float32], sample_rate: int) -> tuple[float, int]:
    """Beats per minute, and how many beats the tracker found.

    Silence - and anything with no clear pulse - comes back as zero from librosa,
    which is not a tempo. It is refused here rather than stored: ``songs.bpm`` has a
    CHECK that would reject a zero, and a made-up tempo would be worse than none.
    """
    estimate, beats = librosa.beat.beat_track(y=samples, sr=sample_rate)

    # librosa 1.0 returns the estimate as a one-element array; earlier versions
    # returned a float. Both are read the same way.
    tempo = float(np.ravel(estimate)[0]) if np.size(estimate) else 0.0
    if not math.isfinite(tempo) or tempo <= 0:
        raise PermanentError(
            FailureCode.UNANALYZABLE, "no tempo could be detected in this recording"
        )

    return tempo, int(np.size(beats))


def detect_key(samples: NDArray[np.float32], sample_rate: int) -> tuple[str, float]:
    """The best-matching key as ``"<tonic> <mode>"``, with its correlation.

    The chroma of the whole recording is averaged into one 12-dimensional profile and
    correlated against each of the 24 keys. Correlation rather than a dot product: it
    is scale-free, so a quiet take and a loud one land on the same key.
    """
    profile = librosa.feature.chroma_cqt(y=samples, sr=sample_rate).mean(axis=1)

    best_score = -math.inf
    best_key = ""
    for tonic, name in enumerate(KEY_NAMES):
        for mode, reference in KEY_PROFILES.items():
            # An undefined correlation is NaN, and every comparison against NaN is
            # False, so a silent profile cannot win - it falls through to the raise.
            score = float(np.corrcoef(np.roll(reference, tonic), profile)[0, 1])
            if score > best_score:
                best_score, best_key = score, f"{name} {mode}"

    if not best_key:
        raise PermanentError(
            FailureCode.UNANALYZABLE, "no tonal content could be detected in this recording"
        )

    return best_key, best_score


def load_samples(path: Path) -> tuple[NDArray[np.float32], int]:
    """Decode the recording to mono float samples at :data:`SAMPLE_RATE`.

    Public because it is the first half of every answer this module gives, and because
    a test that exercises one detector on its own needs the samples the other detectors
    would have been handed.

    A whole track, not a window: tempo and key are claims about the song, and measuring
    the first thirty seconds of a quiet intro would make both of them wrong. A decode
    failure is permanent - the same bytes fail the same way next time.
    """
    try:
        samples, sample_rate = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    except Exception as error:
        # The decoders raise several unrelated types - audioread, libsndfile, the
        # optional backends behind them - and every one of them means the same thing
        # here: these bytes cannot be decoded, and will not decode next time either.
        raise PermanentError(
            FailureCode.DECODE_ERROR, f"cannot decode {path.name}: {error}"
        ) from error

    if samples.size == 0:
        raise PermanentError(FailureCode.DECODE_ERROR, f"{path.name} decoded to no audio")

    return samples, sample_rate
