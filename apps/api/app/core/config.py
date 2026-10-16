"""Application settings.

Read from the environment and from ``apps/api/.env`` (see ``.env.example``).
Our own settings carry the ``MYBAND_`` prefix, third-party credentials keep
their canonical names, so every field declares its alias explicitly.

Import ``get_settings()`` rather than constructing ``Settings`` - it is cached
per process, and building it twice only re-reads the same environment.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/.env, resolved from this file rather than the working directory: the
# service is started from the repo root (`pnpm dev:api`), where a relative ".env"
# would silently load nothing.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Environment-driven configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    env: Literal["development", "staging", "production"] = Field(
        default="development", validation_alias="MYBAND_ENV"
    )
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info", validation_alias="MYBAND_LOG_LEVEL"
    )
    cors_origins: str = Field(
        default="http://localhost:3000", validation_alias="MYBAND_CORS_ORIGINS"
    )

    # --- Analysis pipeline ---
    # Stamped on every analysis_jobs row so a stored result stays interpretable
    # after the pipeline changes (docs/schema.md). Bump it whenever the worker's
    # output shape or algorithms change - a job is billed and read back against
    # the version recorded here.
    #
    # 0.1.0 -> 0.2.0 for the chord timeline: the worker now writes a `chords`
    # artifact, so a 0.1.0 row is one produced without chords.
    # 0.2.0 -> 0.3.0 for the MIDI window: a 0.2.0 row's MIDI describes the first
    # 30 seconds of its recording at most, and a 0.3.0 row's up to 120 - so
    # `summary.window_seconds` is one number with two different meanings, and a
    # note count is only comparable to another of its own version.
    # 0.3.0 -> 0.4.0 for song sections: the worker now writes a `sections`
    # artifact as well, so a 0.4.0 row's `summary` carries a `form` and a
    # section count that a 0.3.0 row does not have.
    pipeline_version: str = Field(default="0.4.0", validation_alias="MYBAND_PIPELINE_VERSION")

    # --- Database (Supabase PostgreSQL) ---
    # The API connects with the project's `postgres` role, which bypasses row
    # level security, so every query has to scope by user_id itself - RLS guards
    # the browser path, not this one (docs/schema.md).
    database_url: str = Field(validation_alias="DATABASE_URL")

    # --- Supabase auth / storage ---
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_role_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    # Only for projects that still sign access tokens with the legacy shared
    # secret (HS256). Projects on asymmetric signing keys - the default, and what
    # 'supabase start' issues locally - are verified against the project's JWKS
    # instead, which needs no secret. See app/core/auth.py.
    supabase_jwt_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="SUPABASE_JWT_SECRET"
    )

    # --- Object storage (Cloudflare R2, S3-compatible) ---
    r2_account_id: str = Field(default="", validation_alias="R2_ACCOUNT_ID")
    r2_access_key_id: SecretStr = Field(default=SecretStr(""), validation_alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="R2_SECRET_ACCESS_KEY"
    )
    r2_bucket: str = Field(default="myband-audio", validation_alias="R2_BUCKET")
    # Overrides the S3 endpoint. Empty means Cloudflare R2
    # (https://<account id>.r2.cloudflarestorage.com); set it to point the same
    # client at Supabase Storage's S3 endpoint locally, or at any other
    # S3-compatible service.
    r2_endpoint_url: str = Field(default="", validation_alias="R2_ENDPOINT_URL")
    # R2 accepts "auto" for any region. A local S3 service may well not, so the
    # region is configuration rather than a constant.
    r2_region: str = Field(default="auto", validation_alias="R2_REGION")

    # --- Uploads (browser -> R2, direct) ---
    # The presigned PUT and uploads.expires_at share this clock, so the URL can
    # never outlive the row that authorized it.
    upload_url_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=604800,
        validation_alias="MYBAND_UPLOAD_URL_TTL_SECONDS",
    )
    # How long a presigned GET stays valid (the MIDI download link). Much shorter than
    # the upload's clock on purpose: an upload has to survive a slow connection, while a
    # download link only has to survive the click that follows the response that carried
    # it. It is also the only thing authorizing the read - the URL *is* the credential.
    download_url_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias="MYBAND_DOWNLOAD_URL_TTL_SECONDS",
    )

    # --- GPU workers (RunPod) ---
    # Carried for the dispatcher, read by nothing yet: that is why they are not in
    # `_require_production_secrets` below, and why a production boot does not ask
    # for them (docs/upload-flow.md, "Deliberately not here yet"). The commit that
    # adds the dispatcher adds them back to that map.
    runpod_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="RUNPOD_API_KEY")
    runpod_endpoint_id: str = Field(default="", validation_alias="RUNPOD_ENDPOINT_ID")

    # --- The analysis worker (`python -m app.workers`) ---
    # One standalone process that claims from `analysis_jobs` and does the work
    # itself. Nothing here is read by the API process.
    #
    # An idle worker polls instead of being notified: one query per interval, no
    # broker, and a queue that can be drained by hand when something needs looking
    # at.
    worker_poll_seconds: float = Field(
        default=5.0, ge=0.5, le=300, validation_alias="MYBAND_WORKER_POLL_SECONDS"
    )
    # How often a running job says it is alive. `queue.STALE_AFTER` (15 minutes) is
    # the deadline this has to beat by a wide margin, or a healthy job gets reaped
    # while it is still working.
    worker_heartbeat_seconds: float = Field(
        default=15.0, ge=1, le=300, validation_alias="MYBAND_WORKER_HEARTBEAT_SECONDS"
    )
    # Tries for one job, transient failures only: a bucket that returned 503 is
    # worth another go, an object that is not there is not.
    worker_max_attempts: int = Field(
        default=3, ge=1, le=10, validation_alias="MYBAND_WORKER_MAX_ATTEMPTS"
    )
    worker_retry_backoff_seconds: float = Field(
        default=2.0, ge=0, le=60, validation_alias="MYBAND_WORKER_RETRY_BACKOFF_SECONDS"
    )
    # Wall-clock budget for one job, checked between stages. It cannot interrupt a
    # detector already running; it stops the worker from spending an hour on a file
    # that will never finish.
    worker_job_timeout_seconds: float = Field(
        default=900.0, ge=30, le=7200, validation_alias="MYBAND_WORKER_JOB_TIMEOUT_SECONDS"
    )
    # How often the loop sweeps for jobs whose worker stopped reporting. A process
    # that was killed cannot fail its own job, so this is the only way out of
    # `running` for it.
    worker_reap_seconds: float = Field(
        default=60.0, ge=5, le=3600, validation_alias="MYBAND_WORKER_REAP_SECONDS"
    )
    # The most of a recording the MIDI sketch is built from - a ceiling, not a
    # slice: a song shorter than this is transcribed whole (whose window it
    # really got is decided per job by `WorkerTuning.midi_window_for`). The pitch
    # tracker costs about a tenth of a second per second of audio, so this is
    # what keeps a long song's job bounded (docs/analysis-worker.md).
    #
    # 30 seconds until this release, 120 here. A window sweep on the three beta
    # recordings (30 s / 60 s / 120 s / whole song, `MIDI_WINDOW_REPORT.md`)
    # measured 2x-4.5x the notes for 3-9 extra seconds of CPU and under 90 MiB,
    # and still two pages of score.
    #
    # Both names read this. `MYBAND_WORKER_MIDI_WINDOW_SECONDS` is the setting's
    # name before it was a cap, and it keeps working because a deployment that
    # sets it is asking for a smaller window, not a different one - silently
    # ignoring it would hand that deployment 120 s after it asked for 30. The
    # legacy name can go once nothing sets it.
    worker_midi_max_window_seconds: int = Field(
        default=120,
        ge=5,
        le=600,
        validation_alias=AliasChoices(
            "MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS",
            "MYBAND_WORKER_MIDI_WINDOW_SECONDS",
        ),
    )

    # --- Operations ---
    # The shared secret for GET /admin/metrics, which is an operator endpoint rather than
    # part of the product: it authenticates with this token, not with a Supabase session
    # (app/api/routes/metrics.py). Empty means the endpoint is published to a local
    # development run only - everywhere else it answers 404 - so a deployment that never
    # sets this cannot accidentally expose its queue.
    metrics_token: SecretStr = Field(default=SecretStr(""), validation_alias="MYBAND_METRICS_TOKEN")

    @property
    def cors_origin_list(self) -> list[str]:
        """``MYBAND_CORS_ORIGINS`` split into a list for CORSMiddleware."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def _require_production_secrets(self) -> "Settings":
        """Fail closed in production, stay convenient in development.

        A deployment that is missing its R2 keys should not boot and then fail one
        upload at a time, so this demands everything the running code reads.
        RunPod's credentials are deliberately absent: nothing calls RunPod yet, and
        asking for them would mean either a placeholder secret or a deploy blocked
        for no functional gain. The dispatcher's commit adds them back here, and
        ``tests/test_config.py`` pins both halves of that.
        """
        if not self.is_production:
            return self
        required = {
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key.get_secret_value(),
            "R2_ACCOUNT_ID": self.r2_account_id,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id.get_secret_value(),
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key.get_secret_value(),
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise ValueError("missing settings required in production: " + ", ".join(missing))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings, read from the environment once per process."""
    return Settings()
