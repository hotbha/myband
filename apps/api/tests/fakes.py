"""Test doubles for the seams the API talks to.

``FakeObjectStore`` implements the ``ObjectStore`` protocol in memory: it records
what it presigned and answers a HEAD with whatever the test put there. That is what
lets the whole upload lifecycle be tested - presign, the object landing, the song,
the job - without a bucket, credentials or a network call.
"""

from dataclasses import dataclass

from app.services.storage import ObjectInfo

PRESIGN_BASE_URL = "https://bucket.test"


class FakeObjectStore:
    """An in-memory object store.

    ``presign_put`` returns a URL that names the key it signed, which is enough for
    a test to see that the key was derived from the caller. ``presign_get`` does the
    same for a download link. ``put`` stands in for the browser's upload;
    ``put_bytes`` and ``download`` are the worker's own write and read, so a pipeline
    test can seed the source audio and then look at what the analysis stored without
    either side knowing about the other.
    """

    def __init__(self) -> None:
        self.objects: dict[str, ObjectInfo] = {}
        self.presigned: list[dict[str, object]] = []
        self.presigned_gets: list[dict[str, object]] = []
        self.bodies: dict[str, bytes] = {}

    def presign_put(self, *, object_key: str, content_type: str, expires_in: int) -> str:
        self.presigned.append(
            {"object_key": object_key, "content_type": content_type, "expires_in": expires_in}
        )
        return f"{PRESIGN_BASE_URL}/{object_key}?X-Amz-Expires={expires_in}"

    def presign_get(
        self,
        *,
        object_key: str,
        expires_in: int,
        filename: str | None = None,
    ) -> str:
        """Remember the download link a caller asked for, and answer with one."""
        self.presigned_gets.append(
            {"object_key": object_key, "expires_in": expires_in, "filename": filename}
        )
        return (
            f"{PRESIGN_BASE_URL}/{object_key}?X-Amz-Expires={expires_in}&X-Amz-SignedHeaders=host"
        )

    def head(self, *, object_key: str) -> ObjectInfo | None:
        return self.objects.get(object_key)

    def download(self, *, object_key: str) -> bytes | None:
        """The object's bytes, or ``None`` when nothing was written at that key."""
        return self.bodies.get(object_key)

    def put_bytes(self, *, object_key: str, body: bytes, content_type: str) -> ObjectInfo:
        """Write an artifact the way the worker does, and remember the bytes."""
        self.bodies[object_key] = body
        self.objects[object_key] = ObjectInfo(
            bytes=len(body),
            content_type=content_type,
            etag="5d41402abc4b2a76b9719d911017c592",
        )
        return self.objects[object_key]

    def put(
        self,
        object_key: str,
        *,
        body_bytes: int,
        body: bytes = b"",
        content_type: str = "audio/mpeg",
        etag: str | None = "5d41402abc4b2a76b9719d911017c592",
    ) -> None:
        """Stand in for the browser: the object now exists in the bucket.

        ``etag`` is the seam's value, already unquoted - stripping S3's quotes is
        the R2 adapter's job, not this fake's. ``body`` is what a worker-side
        ``download`` would read back, and is only needed when a test is going to
        hand the object to the analysis pipeline.
        """
        self.objects[object_key] = ObjectInfo(
            bytes=body_bytes,
            content_type=content_type,
            etag=etag,
        )
        if body:
            self.bodies[object_key] = body

    def delete(self, object_key: str) -> None:
        """Stand in for an object expiring or being swept."""
        self.objects.pop(object_key, None)

    @property
    def last_presigned(self) -> dict[str, object]:
        """What the most recent ``presign_put`` was asked for."""
        return self.presigned[-1]

    @property
    def last_presigned_get(self) -> dict[str, object]:
        """What the most recent ``presign_get`` was asked for."""
        return self.presigned_gets[-1]


@dataclass(frozen=True, slots=True)
class FakeAnalysis:
    """What an analyzer hands back, shape for shape.

    Not an ``AudioAnalysis``, which would drag librosa into every suite that imports
    this module. ``tests/test_worker_analysis.py`` asserts the two have the same fields,
    so the day they drift is the day that test fails rather than the day a pipeline test
    starts passing for the wrong reason.
    """

    duration_ms: int = 8000
    bpm: float = 120.0
    musical_key: str = "A minor"
    key_strength: float = 0.9
    beats: int = 16


@dataclass(frozen=True, slots=True)
class FakeTranscription:
    """What a transcriber hands back, shape for shape. See :class:`FakeAnalysis`."""

    data: bytes = b"MThd\x00\x00\x00\x06fake-midi"
    note_count: int = 3
    window_seconds: int = 30
    name: str = "fake-transcriber"


@dataclass(frozen=True, slots=True)
class FakeChordSegment:
    """One segment, shape for shape with ``chords.ChordSegment``."""

    start_ms: int = 0
    end_ms: int = 4000
    chord: str = "Am"
    confidence: float = 0.9


@dataclass(frozen=True, slots=True)
class FakeChordTimeline:
    """What a chord detector hands back, shape for shape. See :class:`FakeAnalysis`.

    A dumb holder, exactly like the other two: the digest is derived from ``segments`` by
    ``workers.chord_summary``, which the storage layer calls, so there is nothing here to keep in
    step beyond the fields themselves.
    """

    segments: tuple[FakeChordSegment, ...] = (FakeChordSegment(),)
    key: str | None = "A minor"
    name: str = "fake-chord-detector"
    vocabulary: str = "1.0"
    hop_ms: int = 93


@dataclass(frozen=True, slots=True)
class FakeSection:
    """One section, shape for shape with ``sections.Section``."""

    start_ms: int = 0
    end_ms: int = 4000
    label: str = "A"
    confidence: float = 0.8


@dataclass(frozen=True, slots=True)
class FakeSectionTimeline:
    """What a section detector hands back, shape for shape. See :class:`FakeAnalysis`.

    Three sections that say ``A B A``, because a digest read off a single one would not
    exercise the form at all - and a repeat is the one thing a form exists to show. They stop
    at the scripted analysis's 8 000 ms, so the list covers the recording the way a real one
    does.
    """

    sections: tuple[FakeSection, ...] = (
        FakeSection(start_ms=0, end_ms=3000, label="A", confidence=0.9),
        FakeSection(start_ms=3000, end_ms=6000, label="B", confidence=0.7),
        FakeSection(start_ms=6000, end_ms=8000, label="A", confidence=0.8),
    )
    name: str = "fake-section-detector"
    vocabulary: str = "1.0"
    hop_ms: int = 4000


class ScriptedStage:
    """A stage that does what the test scripted: a value, or an exception.

    The last outcome repeats forever, so ``ScriptedStage(FakeAnalysis())`` is a stage
    that always works and ``ScriptedStage(TransientError(...), FakeAnalysis())`` is one
    that fails once. ``calls`` is how a test says "and it never even tried".
    """

    def __init__(self, *outcomes: object) -> None:
        self._outcomes = list(outcomes) or [None]
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class NullHeartbeat:
    """A heartbeat that does nothing, for the tests that are not about heartbeats.

    The real one opens its own connection on a thread, which a test sharing a single
    rolled-back transaction cannot have - and does not need, because what is being
    tested is everything else.
    """

    def __init__(self, *, job_id: object, interval_seconds: float, connect: object = None) -> None:
        self.job_id = job_id
        self.interval_seconds = interval_seconds
        self.beats = 0
        self.started = False
        self.stopped = False

    def start(self) -> "NullHeartbeat":
        self.started = True
        return self

    def stop(self) -> None:
        self.stopped = True

    def __enter__(self) -> "NullHeartbeat":
        return self.start()

    def __exit__(self, *_exc: object) -> bool:
        self.stop()
        return False


class SteppingClock:
    """A clock that advances a fixed step every time it is read.

    Tempo measurements, budgets and durations are all differences between two readings,
    so a test can pin them exactly without sleeping - including the case of a job that
    overruns its budget, which would otherwise take the budget's worth of real time to
    reproduce.
    """

    def __init__(self, step: float = 1.0) -> None:
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        self.now += self.step
        return self.now
