"""Keeping a running job's lease alive while the CPU is busy.

``analysis_jobs.heartbeat_at`` is the only sign the database has that a worker is
alive, and ``queue.reap_stale`` fails any in-flight job that has been quiet for
``queue.STALE_AFTER`` (fifteen minutes). An analysis can take minutes, so the job's own
transactions cannot be what touches that column: they happen at the start and at the
end, and the gap between them is the whole job. A thread does it instead.

The thread opens its own connection for each beat, deliberately. A beat written on the
job's connection would stay invisible to every other session until the job's unit of
work committed - which is exactly the window it exists to cover - and it would be rolled
back with the job if the job failed.

It stops on :meth:`stop`, on the job no longer being in flight (:func:`queue.heartbeat`
returning ``False`` - reaped, finished or cancelled), and on its own errors, which are
logged and retried on the next tick rather than being allowed to kill the job.
"""

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Self
from uuid import UUID

import psycopg

from app.core import db
from app.core.logging import log_fields
from app.services import queue

log = logging.getLogger("myband.worker.heartbeat")

# A floor on the interval, so a caller cannot ask for a beat per microsecond and turn
# the heartbeat into the load it is meant to be smaller than.
MIN_INTERVAL_SECONDS = 0.05

# How long `stop` waits for a beat that is already talking to the database. The thread
# is a daemon, so a database that never answers costs the wait, not the process.
STOP_TIMEOUT_SECONDS = 5.0

ConnectionFactory = Callable[[], AbstractContextManager[psycopg.Connection]]


class Heartbeat:
    """A background thread that says "still working" about one running job.

    A context manager, because that is how the pipeline uses it: entered before the
    first slow stage, left before the job is finished - a heartbeat racing the final
    ``complete`` would be noise at best.
    """

    def __init__(
        self,
        *,
        job_id: UUID,
        interval_seconds: float,
        connect: ConnectionFactory | None = None,
    ) -> None:
        self._job_id = job_id
        self._interval = max(interval_seconds, MIN_INTERVAL_SECONDS)
        self._connect = connect or db.connect
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        # Read by the caller afterwards: how many beats landed, and whether the job
        # was taken away while this worker was busy.
        self.beats = 0
        self.lost = False

    def start(self) -> Self:
        """Begin beating, and return for use as a context manager."""
        self._thread = threading.Thread(
            target=self._beat_forever,
            name=f"heartbeat-{self._job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Ask the thread to finish, and wait briefly for it."""
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=STOP_TIMEOUT_SECONDS)

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *_exc: object) -> bool:
        self.stop()
        return False

    def _beat_forever(self) -> None:
        """Beat every interval until stopped, or until the job is gone.

        The first beat is already written - ``queue.begin`` stamps ``heartbeat_at``
        with ``started_at`` - so this waits before its first write instead of racing
        the statement that just happened.
        """
        while not self._stopped.wait(self._interval):
            if not self._beat():
                return

    def _beat(self) -> bool:
        """One beat. ``False`` means the job is no longer ours and the thread should end."""
        try:
            with self._connect() as conn:
                still_running = queue.heartbeat(conn, job_id=self._job_id)
        except Exception:
            # A database that is briefly unreachable is not a reason to abandon a job
            # that is still being worked on: the next tick tries again, and the job's
            # own lease is long enough to survive several missed beats.
            log.warning(
                "heartbeat failed; will try again on the next interval",
                exc_info=True,
                extra=log_fields(job_id=self._job_id),
            )
            return True

        if not still_running:
            self.lost = True
            log.warning(
                "job is no longer in flight; stopping heartbeats",
                extra=log_fields(job_id=self._job_id, beats=self.beats),
            )
            return False

        self.beats += 1
        return True
