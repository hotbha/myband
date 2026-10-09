"""Structured logs: one JSON object per line.

The analysis worker's output is read by a log service, not by someone tailing a
terminal, so a line has to carry its own fields - job id, song id, stage, elapsed
milliseconds - instead of folding them into a sentence that has to be parsed back
out. Everything a worker logs goes through :func:`log_fields`, so a line is
queryable by `job_id` because the field is really there.

Nothing logs a credential, a full object key payload or an audio byte: the fields
are ids, stage names, counts, durations and error messages that the API's error
shape would have shown a user anyway.

:func:`configure_logging` is called once by a process entry point and is safe to
call again, which matters because tests configure logging too.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

# The four levels `MYBAND_LOG_LEVEL` allows, and what they mean to the parser.
LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# Libraries that log their own traffic or compilation at INFO. Left at their
# default they would bury the worker's own lines - botocore alone logs every retry
# of every S3 call.
QUIET_LOGGERS = (
    "boto3",
    "botocore",
    "librosa",
    "matplotlib",
    "numba",
    "s3transfer",
    "urllib3",
)


class JsonFormatter(logging.Formatter):
    """Render a record as one JSON object, extra fields included."""

    def format(self, record: logging.LogRecord) -> str:
        """The line for ``record``: timestamp, level, logger, message, fields."""
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # `logger.info(..., extra=log_fields(...))`, and never `extra={"message": ...}`:
        # Logging reserves its own attribute names, and clobbering one raises.
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def log_fields(**fields: Any) -> dict[str, Any]:
    """The ``extra`` for a log call, built from keyword fields.

    ``None`` fields are dropped rather than logged as null, so a line says what
    happened instead of listing what did not, and a ``UUID`` becomes its string
    form so the line is valid JSON without the caller remembering to cast it.

    Usage::

        log.info("job started", extra=log_fields(job_id=job.id, attempt=1))
    """
    return {
        "fields": {
            name: (str(value) if isinstance(value, UUID) else value)
            for name, value in fields.items()
            if value is not None
        }
    }


def configure_logging(level: str) -> None:
    """Send the process's logs to stdout as JSON, at ``level``.

    Replaces the root handler instead of adding one, so a second call - the tests,
    or a worker started inside a process that already configured logging - does not
    duplicate every line.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(LOG_LEVELS.get(level.lower(), logging.INFO))

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
