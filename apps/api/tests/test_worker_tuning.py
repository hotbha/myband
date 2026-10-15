"""How much of a recording the MIDI sketch gets.

The window is a cap now, not a fixed slice, and the difference is per job: the setting
says how much a job may spend on the tracker, and the recording says how much of it there
is to transcribe. Both halves are pinned here - the arithmetic, and the path from the
setting to the number the pipeline actually passes.

No database, no audio: ``midi_window_for`` is arithmetic on a duration, which is the point
of it living in ``tuning`` rather than in the MIDI module the pipeline is kept clear of.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.workers import tuning
from app.workers.tuning import WorkerTuning

DEVELOPMENT_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

# The three beta recordings, by the duration the analyzer measured: a jingle, a
# three-minute song and a five-minute one. The numbers below are read off them rather
# than invented, because "the whole song" is a claim about real recordings.
GANESHA_MS = 62_160
JYOTI_MS = 246_800
TERA_SUROOR_MS = 344_895


def tuning_for(cap: int) -> WorkerTuning:
    """Tuning whose only interesting value is the MIDI cap."""
    return WorkerTuning(
        max_attempts=1,
        backoff_seconds=0.0,
        timeout_seconds=3600.0,
        heartbeat_seconds=1.0,
        midi_max_window_seconds=cap,
    )


# --- The clamp ------------------------------------------------------------------


def test_a_recording_that_fits_under_the_cap_is_not_truncated() -> None:
    """A 62 s jingle gets its whole 62 s, rounded up, rather than an arbitrary 30.

    This is the case the fixed window got wrong: ``min()`` here is what makes the
    sketch describe the recording instead of the recording's first half.
    """
    assert tuning_for(120).midi_window_for(GANESHA_MS) == 63


def test_a_recording_longer_than_the_cap_gets_the_cap() -> None:
    """The cap is what keeps a job bounded; a 4:06 song does not get 4:06 of tracker."""
    assert tuning_for(120).midi_window_for(JYOTI_MS) == 120
    assert tuning_for(120).midi_window_for(TERA_SUROOR_MS) == 120


def test_the_cap_is_inclusive() -> None:
    """Exactly the cap is under it, one millisecond past it is the cap - not one more."""
    assert tuning_for(120).midi_window_for(120_000) == 120
    assert tuning_for(120).midi_window_for(120_001) == 120


def test_a_fraction_of_a_second_rounds_up() -> None:
    """The decoder returns only the audio that exists, so rounding up is free.

    Rounding down would drop the tail of anything that runs past a whole number of
    seconds, which is every real recording.
    """
    assert tuning_for(120).midi_window_for(1_200) == 2
    assert tuning_for(120).midi_window_for(8_000) == 8
    assert tuning_for(120).midi_window_for(62_160) == 63


def test_the_answer_never_exceeds_the_recording() -> None:
    """The property both halves share: the window is inside the recording, always."""
    cap = 120
    for duration_ms in (5_000, 30_000, 62_160, 120_000, 246_800, 344_895):
        window = tuning_for(cap).midi_window_for(duration_ms)
        assert 0 < window <= min(cap, (duration_ms + 999) // 1000)


# --- The setting behind it ------------------------------------------------------


def test_a_legacy_cap_still_bounds_a_long_song() -> None:
    """A deployment that set the old name to 30 keeps 30 - it is a smaller cap, not a bug."""
    assert tuning_for(30).midi_window_for(TERA_SUROOR_MS) == 30


def test_a_legacy_cap_still_gives_a_short_song_everything() -> None:
    """And an 8 s recording gets 8 s under it, which the old fixed window could not say."""
    assert tuning_for(30).midi_window_for(8_000) == 8


def test_the_cap_reaches_the_window_through_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wiring, end to end: env var -> Settings -> WorkerTuning -> the number.

    The three hops are three chances to drop the value, and the one that matters is the
    last: a job that reads the wrong setting still transcribes *something*.
    """
    # Pinned: with no ambient MYBAND_ENV this defaults to development anyway, and a
    # production one would make the construct below fail on the secrets it demands
    # rather than on the number this test is about.
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.setenv("MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS", "45")
    monkeypatch.delenv("MYBAND_WORKER_MIDI_WINDOW_SECONDS", raising=False)

    settings = Settings(_env_file=None)
    chosen = WorkerTuning.from_settings(settings)

    assert chosen.midi_max_window_seconds == 45
    assert chosen.midi_window_for(TERA_SUROOR_MS) == 45
    assert chosen.midi_window_for(30_000) == 30


def test_tuning_does_not_drag_the_audio_stack_into_the_pipeline() -> None:
    """``tuning`` imports no audio, which is what lets ``stages`` import it.

    A regression here would not be a wrong number, it would be a slow import in every
    process that touches the pipeline - so it is asserted on the module's own source,
    where the constraint is stated.
    """
    source = Path(tuning.__file__ or "").read_text(encoding="utf-8")

    assert "librosa" not in source
    assert "pretty_midi" not in source
