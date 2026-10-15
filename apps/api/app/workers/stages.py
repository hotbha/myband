"""The work one job does: fetch it, measure it, read its chords, transcribe it, store it.

Kept apart from the pipeline that claims and finishes a job because the two answer
different questions. This module is *what the work costs and how it fails*;
``pipeline.py`` is *which job, and what the database ends up holding*. A stage failure
is raised here, classified in :mod:`app.workers.errors`, and either retried or passed up.

Three policies live here, and each one is deliberate:

* **Retries.** A transient failure is retried in-process with a growing backoff, up to
  ``max_attempts``. A permanent one is never retried: an object that is not in the
  bucket will not appear, and a file that will not decode will not start decoding.
* **The budget.** Checked between stages, because nothing portable can interrupt a
  detector that is already running (there is no SIGALRM on Windows). It stops a file
  that will never finish from holding a worker for hours; it is not a promise that a
  job ends exactly on its deadline.
* **The temp file.** The decoders take paths, so the download is written to one and
  removed when the stages are done, whatever happened.

``analyze``, ``detect_chords`` and ``transcribe`` are injected, and are the only places audio is
touched. That is what lets every policy above be tested without audio, a bucket or a database.
"""

from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from app.core.logging import log_fields
from app.core.problems import ApiProblem, ErrorCode
from app.models.analysis_job import AnalysisJob
from app.services.storage import ObjectStore
from app.workers import artifacts
from app.workers.errors import (
    AnalysisError,
    FailureCode,
    PermanentError,
    TransientError,
)
from app.workers.tuning import WorkerTuning

if TYPE_CHECKING:
    # Typing only: this module must stay importable - and testable - on a machine that
    # never installed the audio stack.
    from app.workers.analysis import AudioAnalysis
    from app.workers.chords import ChordTimeline
    from app.workers.midi import Transcription

    Analyzer = Callable[[Path], AudioAnalysis]
    ChordDetector = Callable[..., ChordTimeline]
    Transcriber = Callable[..., Transcription]

log = logging.getLogger("myband.worker.stages")

StageResult = TypeVar("StageResult")


@dataclass(frozen=True, slots=True)
class Produced:
    """What the stages made: the headline, and where the two payloads landed."""

    analysis: AudioAnalysis
    midi: artifacts.StoredMidi
    chords: artifacts.StoredChords


class Stages:
    """Fetch, measure, transcribe, store - with retries and a budget around them."""

    def __init__(
        self,
        *,
        store: ObjectStore,
        analyze: Analyzer,
        detect_chords: ChordDetector,
        transcribe: Transcriber,
        tuning: WorkerTuning,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._analyze = analyze
        self._detect_chords = detect_chords
        self._transcribe = transcribe
        self._tuning = tuning
        self._sleep = sleep
        self._clock = clock

    def produce(self, job: AnalysisJob, started: float) -> Produced:
        """Everything the job needs, retrying a transient failure with a backoff.

        ``started`` is the clock reading from before the job's first stage, so the
        budget covers the retries and the retries cannot extend it. The budget is
        checked between tries, which is the only portable cancellation point there is.
        """
        attempt = 1
        while True:
            self._check_budget(job, started)
            try:
                return self._stages(job)
            except TransientError as error:
                if attempt >= self._tuning.max_attempts:
                    raise
                delay = self._tuning.backoff_seconds * attempt
                log.warning(
                    "transient failure; retrying",
                    extra=log_fields(
                        job_id=job.id,
                        attempt=attempt,
                        retry_in_seconds=delay,
                        reason=str(error),
                    ),
                )
                self._sleep(delay)
                attempt += 1

    def _stages(self, job: AnalysisJob) -> Produced:
        """The work proper: download, measure, read the chords, transcribe, store.

        The chords are read *before* the pitch tracker runs, and the order is deliberate: they are
        seconds of work and the tracker is the stage that spends a job's whole budget, so the
        cheap answer is in hand before the expensive one can overrun.
        """
        audio = self._download(job)

        with _as_file(audio, job.source_object_key) as path:
            analysis = self._stage(job, "analysis", lambda: self._analyze(path))
            timeline = self._stage(
                job,
                "chords",
                lambda: self._detect_chords(path, key=analysis.musical_key),
            )
            transcription = self._stage(
                job,
                "transcription",
                lambda: self._transcribe(
                    path,
                    bpm=analysis.bpm,
                    # The recording, up to the cap - not the cap, which would slice a
                    # short song to a window it never filled.
                    window_seconds=self._tuning.midi_window_for(analysis.duration_ms),
                ),
            )

        midi = self._stage(job, "store_midi", lambda: self._store_midi(job, transcription))
        chords = self._stage(job, "store_chords", lambda: self._store_chords(job, timeline))

        log.info(
            "analysis produced",
            extra=log_fields(
                job_id=job.id,
                duration_ms=analysis.duration_ms,
                bpm=round(analysis.bpm, 2),
                musical_key=analysis.musical_key,
                notes=midi.note_count,
                chords=chords.segment_count,
            ),
        )
        return Produced(analysis=analysis, midi=midi, chords=chords)

    def _stage(
        self,
        job: AnalysisJob,
        stage: str,
        call: Callable[[], StageResult],
    ) -> StageResult:
        """Run one stage, naming it in the log if that is what failed."""
        try:
            return call()
        except AnalysisError as error:
            log.warning(
                "stage failed",
                extra=log_fields(
                    job_id=job.id,
                    stage=stage,
                    error_code=error.failure_code,
                    message=error.message,
                    retryable=error.retryable,
                ),
            )
            raise

    def _download(self, job: AnalysisJob) -> bytes:
        """The recording, from the bucket.

        A 503 is transient and worth another go. A missing object is not, and is a
        different failure from an empty one: the two need different answers from
        whoever is on call.
        """
        try:
            audio = self._store.download(object_key=job.source_object_key)
        except ApiProblem as error:
            raise _as_failure(error) from error

        if audio is None:
            raise PermanentError(
                FailureCode.SOURCE_MISSING, f"{job.source_object_key} is not in the bucket"
            )
        if not audio:
            raise PermanentError(FailureCode.DECODE_ERROR, f"{job.source_object_key} is empty")

        log.info("source downloaded", extra=log_fields(job_id=job.id, bytes=len(audio)))
        return audio

    def _store_midi(self, job: AnalysisJob, transcription: Transcription) -> artifacts.StoredMidi:
        """Put the MIDI in the bucket, translating its refusal the way a read is."""
        try:
            return artifacts.store_midi(
                self._store,
                user_id=job.user_id,
                job_id=job.id,
                transcription=transcription,
            )
        except ApiProblem as error:
            raise _as_failure(error) from error

    def _store_chords(
        self,
        job: AnalysisJob,
        timeline: ChordTimeline,
    ) -> artifacts.StoredChords:
        """Put the chord timeline in the bucket, translating its refusal the way a read is."""
        try:
            return artifacts.store_chords(
                self._store,
                user_id=job.user_id,
                job_id=job.id,
                timeline=timeline,
            )
        except ApiProblem as error:
            raise _as_failure(error) from error

    def _check_budget(self, job: AnalysisJob, started: float) -> None:
        """Fail a job that has spent its whole budget (see the module docstring)."""
        spent = self._clock() - started
        if spent <= self._tuning.timeout_seconds:
            return

        raise PermanentError(
            FailureCode.ANALYSIS_TIMEOUT,
            f"analysis spent {spent:.0f}s of its {self._tuning.timeout_seconds:.0f}s budget",
        )


def _as_failure(error: ApiProblem) -> AnalysisError:
    """A bucket's problem, as something a job can record and act on.

    ``storage_rejected`` is the bucket answering "no": a policy that does not allow this
    content type, a key it will not accept. No amount of retrying turns that into a yes, so
    it is permanent - and the code it leaves on the job points at the bucket's policy rather
    than sending whoever is on call looking for an outage that is not there. Everything else
    the adapter reports is an outage, which is worth another go.
    """
    if error.code is ErrorCode.STORAGE_REJECTED:
        return PermanentError(FailureCode.STORAGE_REJECTED, error.message)
    return TransientError(FailureCode.STORAGE_UNAVAILABLE, error.message)


@contextmanager
def _as_file(audio: bytes, source_object_key: str) -> Iterator[Path]:
    """The recording on disk for as long as the stages need it, and never after.

    A path rather than a buffer because that is what the decoders take, and a file
    rather than keeping the bytes around because a 200 MiB recording held as bytes
    *and* as decoded samples is memory this process does not have. The suffix is
    carried over from the object key, whose filename is the one the uploader chose:
    the extension is the one hint a decoder wants about the container.
    """
    suffix = Path(source_object_key).suffix or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(audio)
        copy = Path(handle.name)

    try:
        yield copy
    finally:
        # Whatever happened - a detector that raised, a timeout, a bug - the copy goes.
        copy.unlink(missing_ok=True)
