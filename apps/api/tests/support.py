"""Reusable steps for the upload tests.

The same three moves - presign, complete, and "this one has to be refused" - are
made by two suites: the one about what a completed upload becomes
(``test_upload_flow.py``) and the one about what a song reports afterwards
(``test_upload_results.py``). Keeping them here leaves each suite to assert what it
is actually about.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import psycopg
import pytest
from app.core.problems import ApiProblem
from app.services import uploads
from tests.fakes import FakeObjectStore

# A file small enough to be uninteresting, large enough to be plausible.
TWO_KIB = 2048


def start(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    *,
    filename: str = "track.mp3",
    content_type: str | None = "audio/mpeg",
    declared_bytes: int | None = TWO_KIB,
    checksum_sha256: str | None = None,
    now: datetime | None = None,
) -> uploads.StartedUpload:
    """Presign an upload the way the route does."""
    return uploads.start_upload(
        conn,
        store=store,
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        declared_bytes=declared_bytes,
        checksum_sha256=checksum_sha256,
        now=now,
    )


def complete(
    conn: psycopg.Connection,
    store: FakeObjectStore,
    user_id: UUID,
    upload_id: UUID,
    *,
    title: str | None = None,
    artist: str | None = None,
    project_id: UUID | None = None,
) -> uploads.CompletedUpload:
    """Complete an upload the way the route does."""
    return uploads.complete_upload(
        conn,
        store=store,
        user_id=user_id,
        upload_id=upload_id,
        title=title,
        artist=artist,
        project_id=project_id,
    )


def refused(call: Callable[..., object], *args: object, **kwargs: object) -> ApiProblem:
    """Run something that has to refuse, and hand back the problem it raised."""
    with pytest.raises(ApiProblem) as raised:
        call(*args, **kwargs)
    return raised.value
