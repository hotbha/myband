"""One job's lifecycle: claim it, work it, finish it - or lose it.

The order of what happens to a job, and the two places it is written:

1. **claim** - lock the oldest queued job (``FOR UPDATE SKIP LOCKED``) and take it to
   ``running`` in the same transaction (:func:`queue.begin`). The attempt is counted and
   the first heartbeat stamped before any slow work starts.
2. **work** - :class:`app.workers.stages.Stages` fetches the recording, measures it, reads its
   chords, transcribes it and stores the results, with its own retries and budget.
3. **finish** - one transaction writes the artifacts, the job row, ``songs.latest_job_id``
   and the song's ``bpm`` / ``musical_key``. Or one transaction fails the job with a
   reason and a finish time.

**Two transactions, not one**, and the gap between them is the design. A transaction held
across the analysis would make ``heartbeat_at`` invisible to every other session until it
committed - precisely the window the heartbeat exists to cover - and a crashed worker
would lose the work silently. Two transactions also mean the job is genuinely visible as
``running`` while it is being worked on, which is what the UI polls for.

**Idempotency is structural, not a flag.** The claim is a compare-and-swap,
``analysis_results`` upserts on ``(job_id, kind)``, the MIDI key is derived from the job,
and :func:`queue.complete` refuses a job that has left the state this worker believed it
was in. Running the same job twice therefore writes one set of rows and one object - and
the second run is *told* so, rather than being ignored:

* **succeeded** - the result was written.
* **failed** - the job ended with a code and a message; the song's headline stays null.
* **lost** - the work was done but the job had already left this worker's hands (reaped,
  cancelled, finished by someone else), so nothing was written. Not an error: it is why
  two workers can never both write a result. If the MIDI was already put in the bucket it
  stays there, unreferenced, because the guarded write is the only truthful check on
  whether the job is still ours - asking first would be a race, and the key is derived
  from the job, so a re-run overwrites the same object.

Nothing escapes :meth:`Pipeline.process`: even a bug ends as a failed job with
``internal_error``, because a job left in ``running`` with no explanation costs a fifteen
minute reap and tells nobody what went wrong.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import psycopg

from app.core import db
from app.core.logging import log_fields
from app.models import song
from app.models.analysis_job import AnalysisJob
from app.services import queue
from app.services.storage import ObjectStore
from app.workers import artifacts
from app.workers.errors import AnalysisError, FailureCode, PermanentError
from app.workers.heartbeat import Heartbeat
from app.workers.stages import Produced, Stages
from app.workers.tuning import WorkerTuning

if TYPE_CHECKING:
    # Typing only, so the pipeline stays importable without the audio stack installed.
    from app.workers.stages import Analyzer, ChordDetector, Transcriber

log = logging.getLogger("myband.worker.pipeline")

ConnectionFactory = Callable[[], AbstractContextManager[psycopg.Connection]]

# What a job can end as, from this worker's point of view.
Outcome = Literal["succeeded", "failed", "lost"]


@dataclass(frozen=True, slots=True)
class JobOutcome:
    """What happened to one job, in the terms the runner counts in."""

    job_id: UUID
    song_id: UUID
    status: Outcome
    seconds: float
    error_code: str | None = None
    error_message: str | None = None


class Pipeline:
    """Claims queued jobs and runs them through the stages, one at a time.

    Every dependency is injected, and the audio ones are why this class can be tested without a
    bucket, a database or the audio stack: ``analyze``, ``detect_chords`` and ``transcribe`` are
    the only places audio is touched, and ``connect`` is the only place a transaction is.
    """

    def __init__(
        self,
        *,
        store: ObjectStore,
        analyze: Analyzer,
        detect_chords: ChordDetector,
        transcribe: Transcriber,
        connect: ConnectionFactory = db.connect,
        heartbeat_factory: Callable[..., Heartbeat] = Heartbeat,
        tuning: WorkerTuning | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connect = connect
        self._tuning = tuning or WorkerTuning.from_settings()
        # The stages share the tuning, so the budget a job is given and the pace its
        # heartbeat runs at are the same settings read once.
        self._stages = Stages(
            store=store,
            analyze=analyze,
            detect_chords=detect_chords,
            transcribe=transcribe,
            tuning=self._tuning,
            sleep=sleep,
            clock=clock,
        )
        self._heartbeat_factory = heartbeat_factory
        self._clock = clock

    def run_once(self) -> JobOutcome | None:
        """Finish one queued job, or return ``None`` when the queue is empty."""
        claimed = self._claim()
        return None if claimed is None else self.process(claimed)

    def process(self, job: AnalysisJob) -> JobOutcome:
        """Run one claimed job to a terminal state, whatever happens to it.

        The heartbeat covers the stages and nothing else: it is started after the job is
        ``running`` and stopped before the job is finished, because a beat racing the
        final write would be noise at best.
        """
        started = self._clock()
        try:
            with self._heartbeat_factory(
                job_id=job.id,
                interval_seconds=self._tuning.heartbeat_seconds,
                connect=self._connect,
            ) as heartbeat:
                produced = self._stages.produce(job, started)
        except AnalysisError as error:
            return self._fail(job, error, started)
        except Exception as error:
            # A bug, not a stage failure. It is recorded on the job rather than raised,
            # because a job left in `running` with no explanation costs a fifteen minute
            # reap and tells nobody what happened.
            return self._fail(
                job,
                PermanentError(FailureCode.INTERNAL_ERROR, f"{type(error).__name__}: {error}"),
                started,
            )

        return self._finish(job, produced, started, beats=heartbeat.beats)

    def _claim(self) -> AnalysisJob | None:
        """Lock the oldest queued job and take it to ``running``, in one transaction.

        The lock ``claim_next`` takes is what stops a second worker from taking the same
        job, and ``begin`` is what makes it visible as running: together they are the
        handover. The commit that follows releases the lock, which has to happen before
        the heartbeat thread starts writing on its own connection.
        """
        with self._connect() as conn:
            queued = queue.claim_next(conn, limit=1)
            if not queued:
                return None

            job = queue.begin(conn, job=queued[0])
            if job is None:
                log.warning(
                    "a claimed job could not be started; leaving it to whoever holds it",
                    extra=log_fields(job_id=queued[0].id, status=queued[0].status),
                )
                return None

        log.info(
            "job started",
            extra=log_fields(
                job_id=job.id,
                song_id=job.song_id,
                attempt=job.attempts,
                pipeline_version=job.pipeline_version,
            ),
        )
        return job

    def _finish(
        self,
        job: AnalysisJob,
        produced: Produced,
        started: float,
        *,
        beats: int,
    ) -> JobOutcome:
        """Write the result: artifacts, the job row, and the song's headline."""
        seconds = round(self._clock() - started, 3)
        results = artifacts.build_results(
            analysis=produced.analysis,
            midi=produced.midi,
            chords=produced.chords,
        )

        with self._connect() as conn:
            finished = queue.complete(conn, job=job, results=results, compute_seconds=seconds)
            if finished is None:
                # Guarded transition refused: the job is not `running` any more, so
                # this worker no longer owns the answer.
                return self._lost(job, seconds)

            # The same transaction as the pointer, so a library row can never show a
            # finished analysis without the numbers that came with it.
            song.set_analysis(
                conn,
                song_id=job.song_id,
                duration_ms=produced.analysis.duration_ms,
                bpm=produced.analysis.bpm,
                musical_key=produced.analysis.musical_key,
            )

        log.info(
            "job succeeded",
            extra=log_fields(
                job_id=job.id,
                song_id=job.song_id,
                seconds=seconds,
                bpm=round(produced.analysis.bpm, 2),
                musical_key=produced.analysis.musical_key,
                notes=produced.midi.note_count,
                chords=produced.chords.segment_count,
                beats=beats,
            ),
        )
        return JobOutcome(job_id=job.id, song_id=job.song_id, status="succeeded", seconds=seconds)

    def _fail(self, job: AnalysisJob, error: AnalysisError, started: float) -> JobOutcome:
        """Record the reason on the job, and report it to the runner."""
        seconds = round(self._clock() - started, 3)
        with self._connect() as conn:
            failed = queue.fail(
                conn,
                job=job,
                error_code=error.failure_code,
                error_message=error.message,
            )

        if failed is None:
            # The guard refused, so someone else owns this job now and their decision
            # stands. Calling it a failure here would be a lie in the logs.
            return self._lost(job, seconds, error_code=error.failure_code)

        log.error(
            "job failed",
            extra=log_fields(
                job_id=job.id,
                song_id=job.song_id,
                error_code=error.failure_code,
                message=error.message,
                seconds=seconds,
            ),
        )
        return JobOutcome(
            job_id=job.id,
            song_id=job.song_id,
            status="failed",
            seconds=seconds,
            error_code=error.failure_code,
            error_message=error.message,
        )

    def _lost(
        self,
        job: AnalysisJob,
        seconds: float,
        *,
        error_code: str | None = None,
    ) -> JobOutcome:
        """The job no longer belongs to this worker, so its result is discarded."""
        log.warning(
            "job was no longer in flight; the result was discarded",
            extra=log_fields(
                job_id=job.id,
                song_id=job.song_id,
                seconds=seconds,
                error_code=error_code,
            ),
        )
        return JobOutcome(
            job_id=job.id,
            song_id=job.song_id,
            status="lost",
            seconds=seconds,
            error_code=error_code,
        )
