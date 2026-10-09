"""Real audio, synthesized with a known answer.

The analysis tests need recordings whose answer is known *before* a detector looks at
them: a click track at exactly 120 BPM, an arpeggio that is unambiguously in A minor.
Building them here means the expected value is not somebody's guess about a track, and
there is no binary fixture in the repository to keep in sync.

These are real files: 16-bit PCM WAV written by ``soundfile``, read back by the same
libsndfile the pipeline uses in production. The only synthetic thing about them is that
a sine wave is not a cello.
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

SAMPLE_RATE = 44100

# Frequencies of the notes used below, so a test says "A3" instead of 220.0.
A3, C4, E4, A4 = 220.0, 261.626, 329.628, 440.0
C4_LOW, G4, C5 = 261.626, 392.0, 523.251

# The rest of the twelve, for the chord fixtures: a triad is three notes that have to exist by
# name before a test can claim a detector got it right.
F3, G3, B3 = 174.614, 196.0, 246.942
D4 = 293.665

# The bottom of a bass guitar's range, for the fixture that plays an inversion.
E2 = 82.407

# What the loudest sample is scaled to: close enough to full scale to be realistic,
# far enough from it that summing tracks cannot clip into distortion.
PEAK = 0.9


def write_wav(path: Path, samples: NDArray[np.float32], *, sample_rate: int = SAMPLE_RATE) -> Path:
    """Write ``samples`` as a 16-bit PCM WAV, and return the path."""
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    scaled = samples * (PEAK / peak) if peak > 0 else samples
    sf.write(str(path), scaled.astype(np.float32), sample_rate, subtype="PCM_16")
    return path


def sine(
    frequency: float,
    seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.5,
    decay: float = 0.0,
) -> NDArray[np.float32]:
    """A pure tone, optionally decaying (``decay`` per second)."""
    times = np.arange(int(sample_rate * seconds)) / sample_rate
    envelope = np.exp(-decay * times) if decay else 1.0
    return (amplitude * envelope * np.sin(2 * np.pi * frequency * times)).astype(np.float32)


def metronome(bpm: float, seconds: float, *, sample_rate: int = SAMPLE_RATE) -> NDArray[np.float32]:
    """A click on every beat, at exactly ``bpm``.

    A bare pulse, with no pitch, so a tempo test is testing the tracker rather than
    apologising for the material.
    """
    beats = int(seconds * bpm / 60)
    length = int(sample_rate * seconds)
    track = np.zeros(length, dtype=np.float32)

    click = sine(1000.0, 0.02, sample_rate=sample_rate, amplitude=0.8, decay=200.0)
    for beat in range(beats + 1):
        start = round(beat * 60.0 / bpm * sample_rate)
        room = min(len(click), length - start)
        if room > 0:
            track[start : start + room] += click[:room]

    return track


def arpeggio(
    frequencies: list[float],
    note_seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    repeats: int = 1,
) -> NDArray[np.float32]:
    """One note at a time, decaying - monophonic, so a pitch tracker has a fair test.

    The notes are the chord's own pitch classes, which is what makes the expected key
    a fact about the file rather than a guess: A3, C4, E4 is A minor and nothing else.
    """
    notes = frequencies * repeats
    length = int(sample_rate * note_seconds * len(notes))
    track = np.zeros(length, dtype=np.float32)

    for index, frequency in enumerate(notes):
        start = round(index * note_seconds * sample_rate)
        room = min(int(sample_rate * note_seconds), length - start)
        tone = sine(
            frequency,
            room / sample_rate,
            sample_rate=sample_rate,
            amplitude=0.6,
            decay=2.5,
        )
        track[start : start + room] += tone[:room]

    return track


def mix(*tracks: NDArray[np.float32]) -> NDArray[np.float32]:
    """Sum tracks that may differ in length, padding the short ones with silence."""
    length = max(len(track) for track in tracks)
    mixed = np.zeros(length, dtype=np.float32)
    for track in tracks:
        mixed[: len(track)] += track
    return mixed


def chord(
    frequencies: list[float],
    seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.4,
    decay: float = 2.5,
) -> NDArray[np.float32]:
    """Every frequency at once: the polyphony a *chord* detector needs to have anything to read.

    ``arpeggio`` plays one note at a time, which is the right fixture for a pitch tracker. A chord
    is notes sounding *together*, so that is what this produces - and it is why the two fixtures
    exist side by side rather than one serving both.
    """
    track = np.zeros(int(sample_rate * seconds), dtype=np.float32)
    for frequency in frequencies:
        track += sine(frequency, seconds, sample_rate=sample_rate, amplitude=amplitude, decay=decay)
    return track


def progression(
    chords: list[list[float]],
    seconds_each: float,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> NDArray[np.float32]:
    """One chord after another, each held for ``seconds_each``.

    The expected answer is therefore the list that was passed in, chord for chord, which is the
    whole point: a detector is checked against the score it was given, not against a recording
    somebody had an opinion about.
    """
    return np.concatenate(
        [chord(frequencies, seconds_each, sample_rate=sample_rate) for frequencies in chords]
    )


def noise(seconds: float, *, sample_rate: int = SAMPLE_RATE, seed: int = 0) -> NDArray[np.float32]:
    """Deterministic broadband noise: the ingredient that makes a chord hard to read.

    Seeded, so a test that depends on it is a test rather than a coin toss.
    """
    generator = np.random.default_rng(seed)
    samples = generator.standard_normal(int(sample_rate * seconds))
    return (samples * 0.05).astype(np.float32)


def silence(seconds: float, *, sample_rate: int = SAMPLE_RATE) -> NDArray[np.float32]:
    """Nothing at all, which is what a detector has to refuse rather than guess about."""
    return np.zeros(int(sample_rate * seconds), dtype=np.float32)
