"""Response contract for ``GET /admin/metrics``.

An operator's view of the platform: how much work exists, where it is, and whether it
is moving. It is about counts and ages rather than about people - no email address, no
song title, no object key - so the payload can be handed to whoever is on call without
a second thought.
"""

from datetime import datetime

from pydantic import BaseModel


class JobCountsOut(BaseModel):
    """One number per status the schema allows, so a new one cannot hide."""

    queued: int
    dispatched: int
    running: int
    succeeded: int
    failed: int
    canceled: int


class JobActivityOut(BaseModel):
    """What the queue is doing now, and what it did recently."""

    by_status: JobCountsOut
    in_flight: int
    oldest_queued_seconds: float | None = None
    oldest_in_flight_seconds: float | None = None
    finished_recently: int
    failed_recently: int
    reaped_recently: int


class LibraryOut(BaseModel):
    """What the platform holds, as opposed to what it is doing."""

    songs: int
    song_owners: int


class MetricsOut(BaseModel):
    """The whole payload.

    ``oldest_*_seconds`` are null when nothing is in that state, which is the good news
    this endpoint exists to deliver: a null ``oldest_queued_seconds`` means the
    dispatcher is keeping up, and a null ``oldest_in_flight_seconds`` means no worker is
    holding anything. A number that keeps growing is the alert.

    ``reaped_recently`` is the sweep's fingerprint, and is counted separately from
    ``failed_recently`` because the two mean opposite things: an ordinary failure is the
    product working, a reap means a worker died. See docs/queue-state-machine.md.
    """

    generated_at: datetime
    window_seconds: int
    jobs: JobActivityOut
    library: LibraryOut
