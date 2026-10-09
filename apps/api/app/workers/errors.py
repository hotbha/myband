"""How the worker tells two kinds of failure apart, and what it records.

A failed job has to leave a reason behind (``analysis_jobs_failure_reason_check``),
and that reason has to be one of a small, stable set of strings: it is what the
product groups by, what the UI can say something useful about, and what an on-call
engineer greps for. :class:`FailureCode` is that set, and it shares its vocabulary
with the API's ``ErrorCode`` - ``decode_error`` is spelled the same in both, because
the browser is told about the same event.

The distinction that drives the loop is retryability:

* :class:`TransientError` - the bucket answered 503, a connection dropped. The
  worker tries again in-process with a backoff, and the job only records the last
  failure.
* :class:`PermanentError` - the object is not in the bucket, or it is not audio
  this pipeline can read. Another go cannot change that, so the job fails at once.

Anything else that escapes a stage is a bug, and is recorded as ``internal_error``.
A job left in ``running`` with no explanation is worse than one that failed loudly.
"""

from enum import StrEnum


class FailureCode(StrEnum):
    """Stable reasons an analysis can fail. The values fit ``error_code``'s 64 chars.

    Adding one is a compatible change; renaming one breaks every dashboard that
    groups by it.
    """

    # The recording is not there, or is not what it claimed to be.
    SOURCE_MISSING = "source_missing"
    DECODE_ERROR = "decode_error"
    # Readable, but nothing could be measured in it - silence, or noise with no
    # tonal content. Distinct from decode_error: the file is fine, the answer is
    # "there is no answer".
    UNANALYZABLE = "unanalyzable"

    # Our side, and worth another go.
    STORAGE_UNAVAILABLE = "storage_unavailable"
    # Our side, and not worth another go: the bucket refused the request itself - a policy
    # that does not allow this content type, a key it will not accept. Retrying cannot
    # change it, so it is a configuration problem rather than a blip, and the two need
    # different answers from whoever is on call.
    STORAGE_REJECTED = "storage_rejected"

    # Our side, and not worth another go: the job had its whole budget.
    ANALYSIS_TIMEOUT = "analysis_timeout"
    # A bug. The message carries the exception's class, never a stack trace.
    INTERNAL_ERROR = "internal_error"


class AnalysisError(Exception):
    """A stage failure, with the code the job will record."""

    retryable = False

    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def failure_code(self) -> str:
        """The value ``analysis_jobs.error_code`` is given.

        The enum's value, not its name: ``source_missing``, not
        ``FailureCode.SOURCE_MISSING``.
        """
        return str(self.code)


class TransientError(AnalysisError):
    """Worth trying again: the same call could work in a moment."""

    retryable = True


class PermanentError(AnalysisError):
    """Not worth trying again: this input cannot produce a result."""

    retryable = False
