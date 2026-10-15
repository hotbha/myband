"""The worker's tunables, in one place, read from the ``MYBAND_WORKER_*`` settings.

A dataclass rather than five parameters threaded through three objects, because the
values travel together and a test nearly always wants to move one of them:
``WorkerTuning(max_attempts=1, timeout_seconds=0.0)`` is a whole test's worth of setup.

What each value means, and why it is set where it is, is documented where it is
declared - ``app/core/config.py``. This module is only the shape they are passed
around in, and keeps the worker's objects from having to know that settings exist.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class WorkerTuning:
    """How patient one worker is: retries, budget, heartbeats, and the MIDI window."""

    max_attempts: int
    backoff_seconds: float
    timeout_seconds: float
    heartbeat_seconds: float
    midi_max_window_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> WorkerTuning:
        """Read the tuning from the environment (cached settings unless told otherwise).

        ``settings`` is a parameter so a test can hand in a ``Settings`` built from its
        own environment without touching the process-wide cache.
        """
        chosen = settings or get_settings()
        return cls(
            max_attempts=chosen.worker_max_attempts,
            backoff_seconds=chosen.worker_retry_backoff_seconds,
            timeout_seconds=chosen.worker_job_timeout_seconds,
            heartbeat_seconds=chosen.worker_heartbeat_seconds,
            midi_max_window_seconds=chosen.worker_midi_max_window_seconds,
        )

    def midi_window_for(self, duration_ms: int) -> int:
        """How many seconds of ``duration_ms`` of audio the MIDI sketch gets.

        The whole recording, up to the cap: a three-minute song gets the cap, a
        forty-second one gets all forty. A recording is not truncated to a window it
        never filled.

        Rounded up, and deliberately: the decoder returns only the audio that exists,
        so asking for a fraction of a second more than the file holds costs nothing,
        while asking for less silently drops the tail of a song that runs a little
        past a whole number of seconds.

        Lives here rather than in the MIDI module so the pipeline can ask the question
        without importing the audio stack it is kept clear of (see ``stages``).
        """
        return min(math.ceil(duration_ms / 1000), self.midi_max_window_seconds)
