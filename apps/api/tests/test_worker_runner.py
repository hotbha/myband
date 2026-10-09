"""The loop: when it sweeps, when it waits, when it gives up.

No database and no audio: the pipeline and the sweep are handed to the loop, because what
is being asserted is the loop's own scheduling - drain-once, a job cap, the idle wait, the
sweep at startup - rather than anything about a job.
"""

import threading

import pytest
from app.core.ids import new_id
from app.workers.pipeline import JobOutcome
from app.workers.runner import run


class ScriptedPipeline:
    """A pipeline that hands out the outcomes it was given, then nothing.

    ``None`` is an empty queue, which is how the loop finds out it has drained one.
    """

    def __init__(self, *outcomes: JobOutcome | None) -> None:
        self._outcomes = list(outcomes)
        self.claims = 0

    def run_once(self) -> JobOutcome | None:
        self.claims += 1
        return self._outcomes.pop(0) if self._outcomes else None


class StopAfterIdle:
    """A pipeline with nothing to do that asks the loop to stop after two polls.

    Two, not one, so the test can see that an idle loop really does go round again
    instead of exiting quietly the second time it finds nothing.
    """

    def __init__(self, stop: threading.Event, *, polls: int = 2) -> None:
        self._stop = stop
        self._limit = polls
        self.polls = 0

    def run_once(self) -> JobOutcome | None:
        self.polls += 1
        if self.polls >= self._limit:
            self._stop.set()
        return None


class SweepRecorder:
    """Stands in for ``runner.reap``, and counts instead of talking to a database."""

    def __init__(self, *, reaped: int = 0) -> None:
        self.calls = 0
        self.reaped = reaped

    def __call__(self) -> int:
        self.calls += 1
        return self.reaped


@pytest.fixture
def sweep() -> SweepRecorder:
    return SweepRecorder()


def _outcome(status: str = "succeeded") -> JobOutcome:
    return JobOutcome(job_id=new_id(), song_id=new_id(), status=status, seconds=1.0)


def test_once_drains_the_queue_and_returns(sweep: SweepRecorder) -> None:
    """`--once` finishes every queued job, then stops rather than waiting for more."""
    pipeline = ScriptedPipeline(_outcome(), _outcome("failed"))

    summary = run(pipeline=pipeline, once=True, sweep=sweep)

    assert summary.processed == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.idle_polls == 0
    assert pipeline.claims == 3  # the third claim is the one that found nothing


def test_max_jobs_stops_without_looking_for_more(sweep: SweepRecorder) -> None:
    """The cap is checked before claiming, so no work is taken that will not be finished."""
    pipeline = ScriptedPipeline(_outcome(), _outcome(), _outcome())

    summary = run(pipeline=pipeline, max_jobs=2, sweep=sweep)

    assert summary.processed == 2
    assert pipeline.claims == 2


def test_a_failed_job_is_reported_in_the_exit_code(sweep: SweepRecorder) -> None:
    """A cron job or a CI step can tell that something went wrong."""
    assert run(pipeline=ScriptedPipeline(_outcome()), once=True, sweep=sweep).exit_code == 0
    assert run(pipeline=ScriptedPipeline(_outcome("failed")), once=True, sweep=sweep).exit_code == 1


def test_a_lost_job_is_not_a_failure(sweep: SweepRecorder) -> None:
    """Work that was taken away is not the worker's fault, and not an error either."""
    summary = run(pipeline=ScriptedPipeline(_outcome("lost")), once=True, sweep=sweep)

    assert summary.lost == 1
    assert summary.failed == 0
    assert summary.exit_code == 0


def test_an_idle_loop_waits_and_goes_round_again(sweep: SweepRecorder) -> None:
    """An empty queue is a wait, not an exit: the worker is meant to keep running."""
    stopping = threading.Event()
    pipeline = StopAfterIdle(stopping)

    summary = run(pipeline=pipeline, stop=stopping, poll_seconds=0.01, sweep=sweep)

    assert pipeline.polls == 2
    assert summary.idle_polls == 2
    assert summary.processed == 0


def test_the_loop_sweeps_for_orphans_before_it_works(sweep: SweepRecorder) -> None:
    """A job orphaned by a crash is already stale by the time a worker starts."""
    sweep.reaped = 3

    summary = run(pipeline=ScriptedPipeline(_outcome()), once=True, sweep=sweep)

    assert sweep.calls == 1
    assert summary.reaped == 3
