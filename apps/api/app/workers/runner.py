"""The process: claim, work, repeat. ``python -m app.workers``.

A standalone process rather than a route or a thread inside the API. It shares this
service's settings, models and services, and nothing about its lifecycle: it is started,
stopped and scaled on its own, and holds no state a restart would lose. The image it runs
in installs the ``worker`` dependency group; the API image does not.

Three things the loop does besides working:

* **reaps** jobs whose worker stopped reporting (:func:`reap`, backed by
  ``queue.reap_stale``), on its own schedule and once at startup. A process that was
  killed cannot fail its own job, so a sweep is the only way a job leaves ``running``
  after a crash.
* **waits** when the queue is empty - one query per interval, no broker, no busy loop -
  and gives up the wait immediately when a stop signal arrives.
* **stops** on SIGINT/SIGTERM *after* the job in hand. Never in the middle of one:
  abandoning a job leaves it ``running`` until it is reaped, which is correct but costs
  fifteen minutes of a user's time.

``--once`` drains what is queued and exits, which is what a cron-style deployment and the
end-to-end test use.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass

import psycopg

from app.core import db
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, log_fields
from app.services import queue
from app.services.storage import get_object_store
from app.workers.pipeline import JobOutcome, Pipeline
from app.workers.tuning import WorkerTuning

log = logging.getLogger("myband.worker")

ConnectionFactory = Callable[[], AbstractContextManager[psycopg.Connection]]


@dataclass(frozen=True, slots=True)
class LoopSummary:
    """What one run of the loop did. The log line, and the exit code."""

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    lost: int = 0
    idle_polls: int = 0
    reaped: int = 0

    @property
    def exit_code(self) -> int:
        """``0`` unless a job failed, so a cron job or a CI step can notice."""
        return 0 if self.failed == 0 else 1


def run(
    *,
    pipeline: Pipeline | None = None,
    once: bool = False,
    max_jobs: int | None = None,
    stop: threading.Event | None = None,
    connect: ConnectionFactory = db.connect,
    settings: Settings | None = None,
    poll_seconds: float | None = None,
    reap_seconds: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    sweep: Callable[[], int] | None = None,
) -> LoopSummary:
    """Claim and finish jobs until told to stop.

    ``once`` drains whatever is queued and returns, which is how a cron deployment and
    the end-to-end test drive it. ``stop`` is a real event rather than a boolean so an
    idle wait ends the instant a signal arrives instead of up to a poll interval later.

    ``pipeline``, ``connect``, ``clock`` and ``sweep`` exist for the tests: the loop's own
    behaviour - when it sweeps, when it waits, when it gives up - is worth testing without
    a database, and that is only possible if the work, the clock and the sweep are
    injected.

    ``sweep`` is the orphan sweep: by default :func:`reap`, and a test hands in a counter.
    """
    chosen = settings or get_settings()
    worker = pipeline or build_pipeline(settings=chosen)
    stopping = stop or threading.Event()
    sweep_for_orphans = sweep if sweep is not None else lambda: reap(connect=connect)
    poll = chosen.worker_poll_seconds if poll_seconds is None else poll_seconds
    reap_every = chosen.worker_reap_seconds if reap_seconds is None else reap_seconds

    summary = _Counters()
    # Reap on the way in: a job orphaned by a crash is already stale, and this is the
    # first moment anyone can do something about it.
    last_reap = clock() - reap_every

    log.info(
        "worker starting",
        extra=log_fields(
            once=once,
            max_jobs=max_jobs,
            poll_seconds=poll,
            reap_seconds=reap_every,
            pipeline_version=chosen.pipeline_version,
        ),
    )

    while True:
        if stopping.is_set() or (max_jobs is not None and summary.processed >= max_jobs):
            break

        if clock() - last_reap >= reap_every:
            summary.reaped += sweep_for_orphans()
            last_reap = clock()

        outcome = worker.run_once()
        if outcome is None:
            if once:
                break
            summary.idle_polls += 1
            stopping.wait(poll)
            continue

        summary.record(outcome)

    return summary.snapshot()


def reap(*, connect: ConnectionFactory = db.connect) -> int:
    """Fail in-flight jobs whose worker stopped reporting, and say how many.

    Jobs are failed rather than requeued, which is ``queue.reap_stale``'s decision: a
    retry is a new job row, and starting one behind a user's back is a product decision,
    not something a background sweep should make.
    """
    with connect() as conn:
        reaped = queue.reap_stale(conn)

    for job in reaped:
        log.warning(
            "reaped a job whose worker stopped reporting",
            extra=log_fields(job_id=job.id, song_id=job.song_id, status=job.status),
        )
    return len(reaped)


def build_pipeline(*, settings: Settings | None = None) -> Pipeline:
    """The real thing: librosa, pYIN and R2 - the audio stack this process exists for.

    Imported here rather than at module level because the audio stack is a separate
    dependency group: this module, and the loop's tests, must work on a machine that
    never installed it.
    """
    from app.workers.analysis import analyze
    from app.workers.midi import transcribe_with_pyin

    return Pipeline(
        store=get_object_store(),
        analyze=analyze,
        transcribe=transcribe_with_pyin,
        tuning=WorkerTuning.from_settings(settings),
    )


@dataclass(slots=True)
class _Counters:
    """The running tally, handed out frozen."""

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    lost: int = 0
    idle_polls: int = 0
    reaped: int = 0

    def record(self, outcome: JobOutcome) -> None:
        """Count one finished job, under the status it ended as."""
        self.processed += 1
        setattr(self, outcome.status, getattr(self, outcome.status) + 1)

    def snapshot(self) -> LoopSummary:
        """A frozen copy, so a caller cannot mutate what was reported."""
        return LoopSummary(
            processed=self.processed,
            succeeded=self.succeeded,
            failed=self.failed,
            lost=self.lost,
            idle_polls=self.idle_polls,
            reaped=self.reaped,
        )


def _install_signal_handlers(stopping: threading.Event) -> None:
    """Turn Ctrl-C and a container's SIGTERM into "finish this job, then stop".

    ``SIGTERM`` does not exist on every platform, and a process that is not the main
    thread cannot install handlers at all, so both cases are tolerated quietly rather
    than being allowed to stop the worker from starting.
    """

    def _stop(_signum: int, _frame: object) -> None:
        log.info("stop requested; finishing the job in hand")
        stopping.set()

    for name in ("SIGINT", "SIGTERM"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            signal.signal(number, _stop)
        except (ValueError, OSError):
            log.debug("could not install a %s handler", name)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, configure logging and signals, run the loop."""
    parser = argparse.ArgumentParser(
        prog="python -m app.workers",
        description="Analyse queued songs: duration, BPM, key and MIDI.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="drain the queue and exit (a cron deployment, and the end-to-end test)",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        metavar="N",
        help="stop after finishing N jobs",
    )
    arguments = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    stopping = threading.Event()
    _install_signal_handlers(stopping)

    summary = run(
        once=arguments.once,
        max_jobs=arguments.max_jobs,
        stop=stopping,
        settings=settings,
    )

    log.info("worker stopped", extra=log_fields(**asdict(summary)))
    return summary.exit_code
