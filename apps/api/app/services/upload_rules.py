"""The rules for what may be uploaded, as pure functions.

Kept apart from the lifecycle in ``app/services/uploads.py`` on purpose: these are
the decisions that have to hold wherever they are asked - at presign, at completion,
in the tests - and none of them touches a connection, a bucket or a clock.

Every one of them exists twice over: as a check here, and as a CHECK constraint in
``supabase/migrations``. The constants below are what keep the two from drifting
silently - ``uploads_object_key_check`` and ``uploads_checksum_expected_check`` are
asserted against them in ``tests/test_upload_rules.py``.
"""

import re
from http import HTTPStatus
from pathlib import PurePosixPath
from uuid import UUID

from app.core.problems import ApiProblem, ErrorCode
from app.services.storage import ObjectInfo

# 200 MiB. Told to the browser as `max_bytes` and enforced twice: against the size
# the client declares at presign, and against the object's real size at completion.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# Extensions this product accepts, with every MIME type browsers realistically report
# for them. WAV arrives as audio/wav, audio/wave, audio/x-wav or audio/vnd.wave
# depending on the OS; MP3 as audio/mpeg or audio/mp3.
CONTENT_TYPES_BY_EXTENSION: dict[str, frozenset[str]] = {
    "mp3": frozenset({"audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/x-mpeg-3"}),
    "wav": frozenset({"audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"}),
}

# The canonical MIME type for each accepted extension. A client's own spelling is
# accepted when it is an alias, but what gets signed, stored and sent is this one -
# so a WAV declared as audio/x-wav is still recorded as audio/wav.
CANONICAL_CONTENT_TYPE = {"mp3": "audio/mpeg", "wav": "audio/wav"}

ACCEPTED_MESSAGE = "Only MP3 and WAV files can be analysed."
TOO_LARGE_MESSAGE = f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB or smaller."

# Longest filename kept in the object key, extension included. The key itself is
# capped at 512 characters by the schema; this keeps it far below that.
MAX_FILENAME_LENGTH = 120

# A song title from a filename stem has to fit `songs_title_check`.
SONG_TITLE_MAX_LENGTH = 200
FALLBACK_TITLE = "Untitled"

# What a sanitised name looks like when nothing usable survives.
FALLBACK_STEM = "audio"

# `uploads_checksum_expected_check` and `songs_source_checksum_check`.
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

# Anything outside the object key's own alphabet (see `uploads_object_key_check`).
UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def check_object(info: ObjectInfo) -> None:
    """Reject what the bucket says it holds, before a song is built on it.

    This is the second half of the size rule: the first half refuses a *declared*
    size that is too large, this one refuses an object that really is. A client that
    lies at presign time, or skips presign entirely, lands here.
    """
    if info.bytes <= 0:
        raise ApiProblem(
            HTTPStatus.CONFLICT,
            ErrorCode.OBJECT_EMPTY,
            "The uploaded file is empty.",
        )
    if info.bytes > MAX_UPLOAD_BYTES:
        raise ApiProblem(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            ErrorCode.FILE_TOO_LARGE,
            TOO_LARGE_MESSAGE,
        )


def normalize_title(title: str | None) -> str | None:
    """A caller-supplied title, or ``None`` when there is nothing usable in it.

    ``songs_title_check`` wants 1 to 200 characters, so a blank title has to become
    the filename-derived fallback rather than an empty string.
    """
    if title is None:
        return None

    cleaned = title.strip()[:SONG_TITLE_MAX_LENGTH]
    return cleaned or None


def title_from_key(object_key: str) -> str:
    """A song title from the object's filename: ``midnight-drive.mp3`` -> ``midnight-drive``."""
    stem = PurePosixPath(object_key).stem.strip("._-")
    return stem[:SONG_TITLE_MAX_LENGTH] or FALLBACK_TITLE


def normalize_filename(raw: str) -> str:
    """Reduce a client filename to something safe to put in an object key.

    Only the basename survives - ``../../etc/passwd.mp3`` becomes ``passwd.mp3`` - and
    every character outside the key's own alphabet becomes ``_``, which is what keeps
    the result inside ``uploads_object_key_check``. The extension is left alone (case
    included): it is what the accept/reject decision is made on.
    """
    basename = PurePosixPath(raw.replace("\\", "/")).name.strip()
    if not basename or basename in {".", ".."}:
        raise ApiProblem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.INVALID_FILENAME,
            "That filename cannot be used. Rename the file and try again.",
        )

    name = UNSAFE_FILENAME_CHARS.sub("_", basename)
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""

    room = max(MAX_FILENAME_LENGTH - len(extension) - 1, 1)
    safe_stem = stem.strip("._-")[:room] or FALLBACK_STEM

    return f"{safe_stem}.{extension}" if extension else safe_stem


def extension_of(filename: str) -> str:
    """The lowercase extension without its dot, or ``''`` when there is none."""
    _, _, extension = PurePosixPath(filename).name.rpartition(".")
    return extension.lower()


def resolve_content_type(extension: str, declared: str | None) -> str:
    """The MIME type the PUT is signed with.

    The extension decides what is allowed; the client's value is honoured only when it
    is one of the aliases that extension is really reported as. A blank value (curl, a
    desktop client) falls back to the canonical type. Anything else is refused here,
    before an object exists, rather than after it was uploaded.
    """
    allowed = CONTENT_TYPES_BY_EXTENSION.get(extension)
    if allowed is None:
        raise ApiProblem(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            ACCEPTED_MESSAGE,
        )

    if not declared:
        return CANONICAL_CONTENT_TYPE[extension]

    # A client may send "audio/mpeg; charset=..." or nothing but whitespace.
    media_type = declared.split(";")[0].strip().lower()
    if media_type and media_type not in allowed:
        raise ApiProblem(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"{media_type} is not an audio type this service accepts. {ACCEPTED_MESSAGE}",
        )

    return CANONICAL_CONTENT_TYPE[extension]


def build_object_key(*, user_id: UUID, upload_id: UUID, filename: str) -> str:
    """``users/<uid>/uploads/<upload id>/<filename>``, the only key shape allowed.

    Derived from the authenticated user and an upload id this service just generated,
    so a filename from the request body cannot escape the caller's own prefix.
    ``uploads_object_key_check`` asserts the same shape in the database.
    """
    return f"users/{user_id}/uploads/{upload_id}/{filename}"


def check_declared_bytes(declared_bytes: int | None) -> None:
    """Refuse an oversized upload before it happens, when the client told us."""
    if declared_bytes is None:
        return

    if declared_bytes <= 0:
        raise ApiProblem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.INVALID_REQUEST,
            "bytes must be greater than zero.",
        )
    if declared_bytes > MAX_UPLOAD_BYTES:
        raise ApiProblem(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            ErrorCode.FILE_TOO_LARGE,
            TOO_LARGE_MESSAGE,
        )


def normalize_checksum(checksum: str | None) -> str | None:
    """A sha256 digest, lowercased: the columns want 64 lowercase hex characters."""
    if checksum is None:
        return None

    cleaned = checksum.strip().lower()
    if not SHA256_PATTERN.fullmatch(cleaned):
        raise ApiProblem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.INVALID_REQUEST,
            "checksum_sha256 must be a 64 character hex sha256 digest.",
        )

    return cleaned
