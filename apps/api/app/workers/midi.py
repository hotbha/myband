"""The MIDI a job produces, and the seam a full transcriber slots into.

What this is: a **monophonic sketch** of the recording's melody, built from
librosa's pYIN pitch tracker and written as a standard MIDI file (SMF) whose header
carries the detected tempo.

**What this is not: basic-pitch.** That was the plan for this stage, and it cannot
be installed here. ``basic-pitch==0.4.0`` requires ``tensorflow>=2.4.1,<2.15.1`` on
every non-macOS platform, and no version in that range has a wheel for Python 3.12 -
which this project requires - so the resolver refuses it outright ("your project's
requirements are unsatisfiable"). Forcing it in without its declared dependencies and
calling ``predict()`` aborts the interpreter on Windows/py3.12. Shipping it would
mean shipping a dependency nobody can install, so :func:`transcribe_with_pyin` is
what runs and the swap is a change to this module alone (docs/analysis-worker.md).

The one thing to know about pYIN, measured rather than assumed: it costs roughly one
second per second of audio (14.7 s for a 4 s clip at 22 kHz, hop 512). A five minute
song would take most of an hour. So it is given **a bounded window** - the first
``window_seconds`` of the recording, at 11 kHz with a wider hop, which lands near
real time - and the window it used is recorded in the result. A monophonic sketch of
the intro in tens of seconds beats a perfect transcription of the whole track that
never finishes.

A window with nothing to track still produces a file: ``pretty_midi`` writes no track
for an instrument with no notes, so the artifact is a tempo map with no notes in it and
``note_count`` is zero. The job is not a failure - the tempo and key came from the whole
recording and are still stored.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import librosa
import numpy as np
import pretty_midi
from numpy.typing import NDArray

from app.workers.errors import FailureCode, PermanentError

# Half the analysis rate: the pitch tracker's cost is per frame, and nothing it needs
# to see lives above 5.5 kHz. Hop 1024 with a 2048 window is still ~10 ms resolution.
PYIN_SAMPLE_RATE = 11025
FRAME_LENGTH = 2048
HOP_LENGTH = 1024

# The range the tracker is asked about: C2 to C7, which spans bass to soprano.
LOWEST_NOTE = "C2"
HIGHEST_NOTE = "C7"

# A run of one pitch shorter than this is a tracker wobble, not a note. Without it,
# vibrato becomes a cluster of 20 ms notes that no DAW can render usefully.
MIN_VOICED_FRAMES = 3

# A MIDI note cannot be zero length, and the last run's end is the window's edge.
MIN_NOTE_SECONDS = 0.02

NOTE_VELOCITY = 90
INSTRUMENT_NAME = "melody"


@dataclass(frozen=True, slots=True)
class Transcription:
    """MIDI bytes, plus what a reviewer needs to judge how they were made.

    ``name`` travels with the artifact into ``analysis_results.summary``: when the
    transcriber changes, a stored result still says which one produced it.
    """

    data: bytes
    note_count: int
    window_seconds: int
    name: str


def transcribe_with_pyin(path: Path, *, bpm: float, window_seconds: int) -> Transcription:
    """A monophonic MIDI sketch of the recording's first ``window_seconds``.

    This function *is* the seam: the pipeline calls it (or whatever else is passed in
    its place) and does not care how the bytes were produced. ``bpm`` is written into
    the MIDI header so the file lines up with a DAW's grid at the tempo the rest of
    the analysis reports.
    """
    samples, sample_rate = _load_window(path, window_seconds)

    pitch_track, _, _ = librosa.pyin(
        samples,
        fmin=float(librosa.note_to_hz(LOWEST_NOTE)),
        fmax=float(librosa.note_to_hz(HIGHEST_NOTE)),
        sr=sample_rate,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )
    times = librosa.times_like(pitch_track, sr=sample_rate, hop_length=HOP_LENGTH)
    notes = _notes_from_pitch_track(times, pitch_track)

    return Transcription(
        data=render_midi(notes, bpm=bpm),
        note_count=len(notes),
        window_seconds=window_seconds,
        name="pyin-monophonic",
    )


def render_midi(notes: list[tuple[float, float, int]], *, bpm: float) -> bytes:
    """Write ``(start, end, pitch)`` triples as one track of a standard MIDI file.

    Kept separate from the detecting so that what a MIDI file contains is decided in
    one readable place - and so a test can hand it notes without needing audio.
    """
    midi = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
    instrument = pretty_midi.Instrument(program=0, name=INSTRUMENT_NAME, is_drum=False)
    for start, end, pitch in sorted(notes):
        instrument.notes.append(
            pretty_midi.Note(velocity=NOTE_VELOCITY, pitch=pitch, start=start, end=end)
        )
    midi.instruments.append(instrument)

    buffer = BytesIO()
    midi.write(buffer)
    return buffer.getvalue()


def _notes_from_pitch_track(
    times: NDArray[np.float64],
    pitch_track: NDArray[np.float64],
) -> list[tuple[float, float, int]]:
    """Turn a per-frame pitch track into notes.

    One MIDI note per contiguous run of the same rounded pitch. A run shorter than
    :data:`MIN_VOICED_FRAMES`, and any stretch the tracker left unvoiced (NaN), is
    skipped - silence is not a note.
    """
    notes: list[tuple[float, float, int]] = []
    run_start: int | None = None
    run_pitch: int | None = None

    for index, value in enumerate(pitch_track):
        pitch = _pitch_of(value)
        if pitch is None or pitch != run_pitch:
            if run_start is not None and run_pitch is not None:
                closed = _note(times, run_start, index, run_pitch)
                if closed is not None:
                    notes.append(closed)
            run_start, run_pitch = (index, pitch) if pitch is not None else (None, None)

    if run_start is not None and run_pitch is not None:
        closed = _note(times, run_start, len(pitch_track), run_pitch)
        if closed is not None:
            notes.append(closed)

    return notes


def _note(
    times: NDArray[np.float64],
    start: int,
    end: int,
    pitch: int,
) -> tuple[float, float, int] | None:
    """One note from frame indices, or ``None`` when the run is too short to keep."""
    if end - start < MIN_VOICED_FRAMES:
        return None

    starts_at = float(times[start])
    # The last frame of a run is excluded (the next note starts there), and the final
    # run of the window ends at the window's own edge.
    ends_at = float(times[min(end, len(times) - 1)])
    return starts_at, max(ends_at, starts_at + MIN_NOTE_SECONDS), pitch


def _pitch_of(value: float) -> int | None:
    """A frame's pitch as a MIDI note number, or ``None`` when it is not a note."""
    if value is None or not np.isfinite(value):
        return None
    return round(float(librosa.hz_to_midi(value)))


def _load_window(path: Path, window_seconds: int) -> tuple[NDArray[np.float32], int]:
    """The first ``window_seconds`` of the recording, mono, at the tracker's rate.

    ``duration`` is passed to the loader rather than sliced afterwards, so a long file
    is only decoded as far as it is needed.
    """
    try:
        samples, sample_rate = librosa.load(
            str(path),
            sr=PYIN_SAMPLE_RATE,
            mono=True,
            duration=float(window_seconds),
        )
    except Exception as error:
        # One permanent failure for every decoder problem (see analysis._load): these
        # bytes will fail the same way on the next attempt.
        raise PermanentError(
            FailureCode.DECODE_ERROR, f"cannot decode {path.name}: {error}"
        ) from error

    if samples.size == 0:
        raise PermanentError(FailureCode.DECODE_ERROR, f"{path.name} decoded to no audio")

    return samples, sample_rate
