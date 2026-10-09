"""The upload rules, with no database in the way.

Everything here is a decision the API makes before it touches Postgres: which
filenames are usable, which MIME types really are an MP3 or a WAV, how large a file
may be, what a title defaults to, and what an object key looks like.

That these keys and sizes then survive the database's own CHECK constraints is the
other half of the story, and it lives in ``tests/test_upload_flow.py`` - this file
proves the rule, not the row.
"""

import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from app.core.ids import new_id
from app.core.problems import ApiProblem, ErrorCode
from app.services import upload_rules
from app.services.storage import ObjectInfo

# The shape `uploads_object_key_check` and `songs_source_object_key_check` assert,
# so a unit test can spot a key the database would refuse.
OBJECT_KEY_PATTERN = re.compile(r"^users/[0-9a-fA-F-]{36}/[A-Za-z0-9._/-]+$")


def _rejected(call: Callable[..., Any], *args: object, **kwargs: object) -> ApiProblem:
    """Run a rule that must refuse, and hand back what it refused with."""
    with pytest.raises(ApiProblem) as raised:
        call(*args, **kwargs)
    return raised.value


# --- Filenames ---------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["track.mp3", "TRACK.MP3", "track.wav", "track.WAV", "little wing.wav"],
)
def test_accepts_a_filename_it_can_build_a_key_from(filename: str) -> None:
    assert upload_rules.normalize_filename(filename)


def test_keeps_the_extension_case_but_reads_it_case_insensitively() -> None:
    assert upload_rules.normalize_filename("Track.MP3").endswith(".MP3")
    assert upload_rules.extension_of("Track.MP3") == "mp3"


def test_strips_every_directory_from_the_name() -> None:
    """A traversal attempt becomes an ordinary filename inside the caller's prefix."""
    assert upload_rules.normalize_filename("../../etc/passwd.mp3") == "passwd.mp3"
    assert upload_rules.normalize_filename(r"C:\Users\me\song.wav") == "song.wav"


def test_replaces_characters_an_object_key_cannot_hold() -> None:
    assert upload_rules.normalize_filename("my song!.mp3") == "my_song.mp3"
    assert upload_rules.normalize_filename("...leading.dots.wav") == "leading.dots.wav"


def test_caps_a_filename_that_is_absurdly_long() -> None:
    name = upload_rules.normalize_filename("a" * 400 + ".mp3")

    assert len(name) <= upload_rules.MAX_FILENAME_LENGTH
    assert name.endswith(".mp3")


@pytest.mark.parametrize("raw", ["", "   ", ".", "..", "/"])
def test_refuses_a_filename_with_nothing_usable_left(raw: str) -> None:
    problem = _rejected(upload_rules.normalize_filename, raw)

    assert problem.status == 422
    assert problem.code is ErrorCode.INVALID_FILENAME


# --- Content types -----------------------------------------------------------


@pytest.mark.parametrize(
    "declared",
    ["audio/mpeg", "audio/mp3", "AUDIO/MPEG", "audio/mpeg; charset=utf-8"],
)
def test_accepts_every_alias_of_an_mp3(declared: str) -> None:
    assert upload_rules.resolve_content_type("mp3", declared) == "audio/mpeg"


@pytest.mark.parametrize("declared", ["audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"])
def test_accepts_every_alias_of_a_wav(declared: str) -> None:
    assert upload_rules.resolve_content_type("wav", declared) == "audio/wav"


@pytest.mark.parametrize("declared", [None, "", "   "])
def test_infers_the_content_type_when_the_client_sends_none(declared: str | None) -> None:
    assert upload_rules.resolve_content_type("mp3", declared) == "audio/mpeg"
    assert upload_rules.resolve_content_type("wav", declared) == "audio/wav"


@pytest.mark.parametrize(
    ("extension", "declared"),
    [
        ("flac", "audio/flac"),
        ("ogg", None),
        ("", "audio/mpeg"),
        ("mp3", "audio/wav"),
        ("wav", "application/octet-stream"),
        ("mp3", "text/plain"),
    ],
)
def test_refuses_anything_that_is_not_an_mp3_or_a_wav(extension: str, declared: str | None) -> None:
    problem = _rejected(upload_rules.resolve_content_type, extension, declared)

    assert problem.status == 415
    assert problem.code is ErrorCode.UNSUPPORTED_MEDIA_TYPE


def test_the_workers_midi_artifact_is_not_an_upload_type() -> None:
    """``audio/midi`` is in the bucket policy for the worker, not for the browser.

    A MIDI file is something this product *produces*. Accepting one as an input would add
    a source of audio nothing decodes, so it is refused like any other type the product
    does not take - and it is in no alias set, which is what keeps the bucket's
    ``allowed_mime_types`` from reading as if a browser could send one.
    """
    aliases = {
        declared
        for allowed in upload_rules.CONTENT_TYPES_BY_EXTENSION.values()
        for declared in allowed
    }

    assert "audio/midi" not in aliases
    for extension in ("mid", "midi"):
        assert _rejected(upload_rules.resolve_content_type, extension, "audio/midi").status == 415


# --- The content-type tables themselves ---------------------------------------


def test_both_tables_describe_the_same_set_of_extensions() -> None:
    """One decision written twice, so a key in one and not the other is a bug.

    Missing from ``CANONICAL_CONTENT_TYPE`` means an accepted file cannot be signed;
    missing from ``CONTENT_TYPES_BY_EXTENSION`` means a type nothing accepts.
    """
    assert set(upload_rules.CONTENT_TYPES_BY_EXTENSION) == set(upload_rules.CANONICAL_CONTENT_TYPE)


@pytest.mark.parametrize("extension", sorted(upload_rules.CONTENT_TYPES_BY_EXTENSION))
def test_every_alias_of_an_extension_canonicalises_to_the_same_type(extension: str) -> None:
    """Parametrized over the table rather than over a hand-written list, so an alias
    added to the table is covered the moment it exists."""
    canonical = upload_rules.CANONICAL_CONTENT_TYPE[extension]

    assert canonical in upload_rules.CONTENT_TYPES_BY_EXTENSION[extension]
    for alias in sorted(upload_rules.CONTENT_TYPES_BY_EXTENSION[extension]):
        assert upload_rules.resolve_content_type(extension, alias) == canonical


def test_no_type_is_an_alias_of_two_extensions() -> None:
    """A shared type would let one extension be signed as another."""
    claimed: dict[str, str] = {}

    for extension, aliases in upload_rules.CONTENT_TYPES_BY_EXTENSION.items():
        for alias in aliases:
            assert alias not in claimed, f"{alias} is claimed by {claimed[alias]} and {extension}"
            claimed[alias] = extension


def test_every_alias_is_a_well_formed_media_type() -> None:
    """Lowercase ``type/subtype`` with no parameters: this string is signed, stored on
    the object, and compared against the bucket's own policy."""
    for aliases in upload_rules.CONTENT_TYPES_BY_EXTENSION.values():
        for alias in aliases:
            assert re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", alias), alias


# --- Size --------------------------------------------------------------------


def test_accepts_the_cap_and_refuses_one_byte_over_it() -> None:
    upload_rules.check_declared_bytes(upload_rules.MAX_UPLOAD_BYTES)

    problem = _rejected(upload_rules.check_declared_bytes, upload_rules.MAX_UPLOAD_BYTES + 1)

    assert problem.status == 413
    assert problem.code is ErrorCode.FILE_TOO_LARGE


@pytest.mark.parametrize("declared", [0, -1])
def test_refuses_a_declared_size_that_is_not_positive(declared: int) -> None:
    assert _rejected(upload_rules.check_declared_bytes, declared).status == 422


def test_allows_a_client_that_declares_nothing() -> None:
    upload_rules.check_declared_bytes(None)


def test_the_real_object_is_measured_against_the_same_cap() -> None:
    """A client that understates its size at presign time is caught here instead."""
    upload_rules.check_object(ObjectInfo(bytes=1024, content_type="audio/mpeg", etag=None))
    upload_rules.check_object(
        ObjectInfo(bytes=upload_rules.MAX_UPLOAD_BYTES, content_type="audio/mpeg", etag=None)
    )

    too_big = _rejected(
        upload_rules.check_object,
        ObjectInfo(bytes=upload_rules.MAX_UPLOAD_BYTES + 1, content_type=None, etag=None),
    )
    assert too_big.status == 413

    empty = _rejected(
        upload_rules.check_object,
        ObjectInfo(bytes=0, content_type="audio/mpeg", etag=None),
    )
    assert empty.status == 409
    assert empty.code is ErrorCode.OBJECT_EMPTY


# --- Checksums ---------------------------------------------------------------


def test_lowercases_a_checksum_and_refuses_anything_that_is_not_a_digest() -> None:
    assert upload_rules.normalize_checksum("A" * 64) == "a" * 64
    assert upload_rules.normalize_checksum(None) is None

    for bad in ("abc", "z" * 64, "a" * 63, "a" * 65):
        assert _rejected(upload_rules.normalize_checksum, bad).status == 422


# --- Object keys -------------------------------------------------------------


def test_the_key_is_scoped_to_the_user_and_the_upload() -> None:
    user_id, upload_id = new_id(), new_id()

    key = upload_rules.build_object_key(user_id=user_id, upload_id=upload_id, filename="track.mp3")

    assert key == f"users/{user_id}/uploads/{upload_id}/track.mp3"
    assert OBJECT_KEY_PATTERN.fullmatch(key)


def test_even_a_maximal_filename_stays_inside_the_column() -> None:
    key = upload_rules.build_object_key(
        user_id=new_id(),
        upload_id=new_id(),
        filename=upload_rules.normalize_filename("a" * 400 + ".wav"),
    )

    assert len(key) <= 512
    assert OBJECT_KEY_PATTERN.fullmatch(key)


def test_a_key_is_shaped_the_way_the_schema_says() -> None:
    key = upload_rules.build_object_key(
        user_id=UUID("018f2f3a-1111-7000-8000-000000000001"),
        upload_id=UUID("018f2f3a-2222-7000-8000-000000000002"),
        filename="mix_2.wav",
    )

    assert key.startswith("users/018f2f3a-1111-7000-8000-000000000001/uploads/")
    assert key.endswith("/018f2f3a-2222-7000-8000-000000000002/mix_2.wav")
    assert OBJECT_KEY_PATTERN.fullmatch(key)


# --- Titles ------------------------------------------------------------------


def test_a_song_is_named_after_the_file_it_came_from() -> None:
    filename = upload_rules.normalize_filename("midnight drive.wav")
    key = upload_rules.build_object_key(user_id=new_id(), upload_id=new_id(), filename=filename)

    assert upload_rules.title_from_key(key) == "midnight_drive"


def test_a_title_has_to_hold_something() -> None:
    assert upload_rules.normalize_title(None) is None
    assert upload_rules.normalize_title("   ") is None
    assert upload_rules.normalize_title("  Songs  ") == "Songs"
    assert len(upload_rules.normalize_title("x" * 500) or "") == upload_rules.SONG_TITLE_MAX_LENGTH


def test_a_title_survives_a_filename_that_is_all_punctuation() -> None:
    key = upload_rules.build_object_key(user_id=new_id(), upload_id=new_id(), filename="___.wav")

    assert upload_rules.title_from_key(key) == upload_rules.FALLBACK_TITLE
