"""Scaffolding for the worker's database suites.

The same four moves - tune a worker, point it at this transaction, queue a job for a song,
and stand in for the bucket - are made by both ``test_worker_pipeline.py`` and
``test_worker_pipeline_failures.py``. Keeping them here leaves each suite to assert what it
is actually about, the way ``tests/support.py`` does for the upload suites.

The audio stack is deliberately absent: the analyzer, the chord detector and the transcriber are
scripted, so these suites need no librosa, no real recording and no bucket - and a stage failure
becomes something a test can ask for exactly, instead of something it has to provoke.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from http import HTTPStatus
from uuid import UUID

import psycopg
from app.core.problems import ApiProblem, ErrorCode
from app.models.analysis_job import AnalysisJob
from app.services import queue
from app.services.storage import ObjectInfo
from app.workers.pipeline import Pipeline
from app.workers.tuning import WorkerTuning
from tests.fakes import (
    FakeAnalysis,
    FakeChordTimeline,
    FakeObjectStore,
    FakeTranscription,
    NullHeartbeat,
    ScriptedStage,
    SteppingClock,
)

# Stands in for what a browser uploaded. The pipeline hands these bytes to the decoders and
# never inspects them itself, so 300 bytes of anything is the whole requirement.
SOURCE_AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 256


def tuning(**overrides: object) -> WorkerTuning:
    """Tuning with no waiting and no surprises, unless a test asks for one."""
    chosen: dict[str, object] = {
        "max_attempts": 1,
        "backoff_seconds": 0.0,
        "timeout_seconds": 3600.0,
        "heartbeat_seconds": 0.05,
        "midi_window_seconds": 30,
    }
    chosen.update(overrides)
    return WorkerTuning(**chosen)  # type: ignore[arg-type]


def transactions(
    conn: psycopg.Connection,
) -> Callable[[], AbstractContextManager[psycopg.Connection]]:
    """A connection factory that hands back the test's own connection.

    The pipeline owns its transaction boundaries - two per job - and this is how a test
    keeps both inside the one the ``conn`` fixture rolls back.
    """

    @contextmanager
    def factory() -> Iterator[psycopg.Connection]:
        yield conn

    return factory


def worker(conn: psycopg.Connection, store: FakeObjectStore, **overrides: object) -> Pipeline:
    """A pipeline wired to this test's transaction, with the audio stack scripted."""
    return Pipeline(
        store=store,
        analyze=overrides.pop("analyze", ScriptedStage(FakeAnalysis())),
        detect_chords=overrides.pop("detect_chords", ScriptedStage(FakeChordTimeline())),
        transcribe=overrides.pop("transcribe", ScriptedStage(FakeTranscription())),
        connect=transactions(conn),
        heartbeat_factory=NullHeartbeat,
        tuning=overrides.pop("tuning", tuning()),
        sleep=overrides.pop("sleep", lambda _seconds: None),
        clock=overrides.pop("clock", SteppingClock()),
    )


def queued(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    *,
    user_id: UUID,
    song_id: UUID,
    make_object_key: Callable[..., str],
    audio: bytes | None = SOURCE_AUDIO,
) -> AnalysisJob:
    """A queued job for ``song_id``, with its recording already in the bucket."""
    key = make_object_key(name="track.wav")
    if audio is not None:
        store.put(key, body_bytes=len(audio), body=audio, content_type="audio/wav")

    outcome = queue.enqueue(
        conn,
        user_id=user_id,
        song_id=song_id,
        pipeline_version="0.1.0",
        source_object_key=key,
    )
    assert outcome.job is not None
    return outcome.job


class UnavailableStore(FakeObjectStore):
    """A bucket that refuses its first ``failures`` reads, the way a 503 would."""

    def __init__(self, *, failures: int) -> None:
        super().__init__()
        self.remaining = failures

    def download(self, *, object_key: str) -> bytes | None:
        if self.remaining > 0:
            self.remaining -= 1
            raise ApiProblem(
                HTTPStatus.SERVICE_UNAVAILABLE,
                ErrorCode.STORAGE_UNAVAILABLE,
                "storage is down",
            )
        return super().download(object_key=object_key)


class RejectingStore(FakeObjectStore):
    """A bucket that refuses the artifact itself, the way a 415 on a policy would."""

    def put_bytes(self, *, object_key: str, body: bytes, content_type: str) -> ObjectInfo:
        raise ApiProblem(
            HTTPStatus.BAD_GATEWAY,
            ErrorCode.STORAGE_REJECTED,
            "Object storage refused the request: its policy does not allow it.",
        )
