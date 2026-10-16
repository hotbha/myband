"""One complete analysis: upload, queue, process, results.

The only suite that uses all three real parts at once - the upload lifecycle against a real
bucket, the worker against real tempo, key, chord, section and MIDI detection, and a real
database - because the question it answers is "does the product work", which no arrangement of
fakes can answer.

It is the slow one: a real HTTP PUT to the bucket, a real decode, a real transcription.
That is the point, so it is gated behind its own flag rather than running with the rest::

    pnpm dlx supabase@latest start
    $env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    $env:MYBAND_E2E = "1"
    uv run --directory apps/api --group worker pytest tests/test_worker_e2e.py -v

``R2_ENDPOINT_URL`` and the ``R2_*`` keys in ``apps/api/.env`` have to point at that stack,
and the ``myband-audio`` bucket has to exist (see docs/upload-flow.md).
"""

import os
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import boto3
import httpx
import psycopg
import pytest
from app.core.config import get_settings
from app.core.db import connect
from app.models import analysis_job, analysis_result, song
from app.models.analysis_job import AnalysisJob
from app.services import queue, uploads
from app.services.storage import get_object_store
from app.workers import analysis, chords, midi, sections
from app.workers.pipeline import Pipeline
from botocore.config import Config
from tests import audio

pytestmark = pytest.mark.skipif(
    not (os.environ.get("MYBAND_TEST_DATABASE_URL") and os.environ.get("MYBAND_E2E")),
    reason="set MYBAND_TEST_DATABASE_URL and MYBAND_E2E=1 to run the end-to-end analysis",
)

pytest.importorskip("librosa", reason="needs the worker dependency group")

TEST_DATABASE_URL = os.environ.get("MYBAND_TEST_DATABASE_URL", "")

# The recording the test uploads: eight seconds of a 120 BPM pulse with an A minor
# arpeggio over it, so tempo, key and MIDI all have an answer that was decided before the
# detectors looked.
SONG_SECONDS = 8.0
EXPECTED_BPM = 120.0
EXPECTED_KEY = "A minor"

# The API's own account of the file: a WAV named like a track.
FILENAME = "e2e-track.wav"
CONTENT_TYPE = "audio/wav"


class _AnalysesOnlyThisSong(Pipeline):
    """The real pipeline, claiming one song's job and nothing else.

    ``claim_next`` takes the *oldest* queued job in the table, and this database is shared
    with the seed: without this, the test would analyse whatever the seed left behind. Only
    the claim is narrowed - the stages, the store, the detectors and the writes are the
    ones the worker process uses.
    """

    def __init__(self, *, song_id: UUID, **dependencies: object) -> None:
        super().__init__(**dependencies)  # type: ignore[arg-type]
        self._song_id = song_id

    def claim_mine(self) -> AnalysisJob | None:
        """Claim and start this song's job: the loop's first transaction, on one job."""
        with self._connect() as conn:
            for candidate in queue.claim_next(conn, limit=queue.MAX_BATCH):
                if candidate.song_id == self._song_id:
                    return queue.begin(conn, job=candidate)
        return None


def test_an_uploaded_song_is_analysed_end_to_end(
    tmp_path: Path,
    make_user: Callable[..., UUID],
    settings_env: None,
) -> None:
    """Upload, queue, process, results - each step read back from the database.

    One test rather than five, because the path only means anything as a whole: the point
    is that the bytes a browser sent are the bytes the worker analysed, and that the song
    the upload created is the song the results land on.
    """
    store = get_object_store()
    recording = audio.write_wav(
        tmp_path / FILENAME,
        audio.mix(
            audio.metronome(EXPECTED_BPM, SONG_SECONDS),
            audio.arpeggio([audio.A3, audio.C4, audio.E4, audio.A4], 0.5, repeats=4),
        ),
    )
    uploaded = recording.read_bytes()
    upload_key: str | None = None
    midi_key: str | None = None
    chords_key: str | None = None
    sections_key: str | None = None

    with connect(url=TEST_DATABASE_URL) as conn:
        user_id = make_user(on=conn)
        conn.commit()
        try:
            # --- 1. Upload: the API signs a URL, the browser fills it, the API confirms ---
            started = uploads.start_upload(
                conn,
                store=store,
                user_id=user_id,
                filename=FILENAME,
                content_type=CONTENT_TYPE,
                declared_bytes=len(uploaded),
            )
            upload_key = started.upload.object_key

            response = httpx.put(
                started.upload_url,
                content=uploaded,
                headers={"Content-Type": CONTENT_TYPE},
                timeout=30.0,
            )
            assert response.status_code == 200, response.text

            completed = uploads.complete_upload(
                conn,
                store=store,
                user_id=user_id,
                upload_id=started.upload.id,
                title="End To End",
            )
            assert completed.job is not None
            job_id = completed.job.id
            song_id = completed.song.id
            conn.commit()

            # --- 2. Queued, with nothing measured yet --------------------------------
            queued = analysis_job.get(conn, job_id)
            assert queued is not None
            assert queued.status == "queued"
            assert queued.source_object_key == upload_key
            # The upload knows the file's size, not its length: only a decode can say how
            # long the recording is, which is why the worker writes that column.
            assert song.get(conn, song_id).duration_ms is None

            # The worker, exactly as the process builds it: real bucket, real detectors.
            worker = _AnalysesOnlyThisSong(
                song_id=song_id,
                store=store,
                analyze=analysis.analyze,
                detect_chords=chords.detect_chords,
                detect_sections=sections.detect_sections,
                transcribe=midi.transcribe_with_pyin,
            )

            # --- 3. Processing: claimed and started, visible to every other session ---
            claimed = worker.claim_mine()
            assert claimed is not None
            assert claimed.id == job_id
            assert analysis_job.get(conn, job_id).status == "running"
            assert analysis_job.get(conn, job_id).heartbeat_at is not None

            # --- 4. Completed, with the analysis on the song -------------------------
            outcome = worker.process(claimed)
            assert outcome.status == "succeeded", outcome.error_message
            assert outcome.error_code is None

            # --- 5. What the database holds ------------------------------------------
            finished = analysis_job.get(conn, job_id)
            assert finished is not None
            assert finished.status == "succeeded"
            assert finished.attempts == 1
            assert finished.error_code is None
            assert finished.started_at is not None
            assert finished.finished_at is not None
            assert finished.compute_seconds is not None

            analysed = song.get(conn, song_id)
            assert analysed is not None
            assert analysed.latest_job_id == job_id
            assert analysed.duration_ms == pytest.approx(SONG_SECONDS * 1000, abs=50)
            # `numeric` columns come back as Decimal, so the comparison is made in floats.
            assert float(analysed.bpm) == pytest.approx(EXPECTED_BPM, rel=0.08)
            assert analysed.musical_key == EXPECTED_KEY

            rows = {row.kind: row for row in analysis_result.list_for_job(conn, job_id)}
            assert set(rows) == {"bpm", "key", "chords", "sections", "midi"}
            assert rows["bpm"].summary["bpm"] == pytest.approx(EXPECTED_BPM, rel=0.08)
            assert rows["key"].summary["key"] == EXPECTED_KEY

            # The chords, read off the same audio the tempo and key came from.
            chords_row = rows["chords"]
            assert chords_row.object_key is not None
            chords_key = chords_row.object_key
            assert chords_row.summary["detector"] == "librosa-chroma-viterbi"
            assert chords_row.summary["segments"] > 0
            assert "Am" in chords_row.summary["progression"]
            chords_head = store.head(object_key=chords_key)
            assert chords_head is not None
            assert chords_head.bytes == chords_row.object_bytes
            assert chords_head.content_type == "application/json"

            midi_row = rows["midi"]
            assert midi_row.object_key is not None
            midi_key = midi_row.object_key
            assert midi_row.summary["transcriber"] == "pyin-monophonic"
            assert midi_row.summary["notes"] > 0
            # The artifact the row points at is really in the bucket, and the two agree.
            head = store.head(object_key=midi_key)
            assert head is not None
            assert head.bytes == midi_row.object_bytes
            assert head.content_type == "audio/midi"

            # The sections, read off the same audio and stored beside the chords.
            sections_row = rows["sections"]
            assert sections_row.object_key is not None
            sections_key = sections_row.object_key
            assert sections_row.summary["detector"] == "chroma-pool-cluster-viterbi"
            assert sections_row.summary["sections"] >= 1
            # Eight seconds is one piece of music however it is cut, so its form is one letter.
            assert sections_row.summary["form"] == "A"
            sections_head = store.head(object_key=sections_key)
            assert sections_head is not None
            assert sections_head.bytes == sections_row.object_bytes
            assert sections_head.content_type == "application/json"
        finally:
            _clean_up(
                conn,
                user_id=user_id,
                keys=[upload_key, midi_key, chords_key, sections_key],
            )


def _clean_up(conn: psycopg.Connection, *, user_id: UUID, keys: list[str | None]) -> None:
    """Remove the row and the objects this test made, whatever happened.

    The rows go with the account (``auth.users`` cascades into songs, their jobs and the
    results). The objects are removed by hand: the API has no delete - that is what
    ``storage_gc_queue`` is for - and a test that left them behind would leave the bucket
    growing.
    """
    conn.rollback()
    conn.execute("delete from auth.users where id = %s", (user_id,))
    conn.commit()

    settings = get_settings()
    client = _s3_client()
    for key in keys:
        if key:
            client.delete_object(Bucket=settings.r2_bucket, Key=key)


def _s3_client() -> object:
    """A client for the same bucket the API uses, to tidy up after the test."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url.rstrip("/") or None,
        aws_access_key_id=settings.r2_access_key_id.get_secret_value() or None,
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value() or None,
        region_name=settings.r2_region,
        config=Config(signature_version="s3v4"),
    )
