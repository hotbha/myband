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

from pydantic import Field, SecretStr, model_validator
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
    pipeline_version: str = Field(default="0.1.0", validation_alias="MYBAND_PIPELINE_VERSION")

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

    # --- GPU workers (RunPod) ---
    runpod_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="RUNPOD_API_KEY")
    runpod_endpoint_id: str = Field(default="", validation_alias="RUNPOD_ENDPOINT_ID")

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
        upload at a time.
        """
        if not self.is_production:
            return self
        required = {
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key.get_secret_value(),
            "R2_ACCOUNT_ID": self.r2_account_id,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id.get_secret_value(),
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key.get_secret_value(),
            "RUNPOD_API_KEY": self.runpod_api_key.get_secret_value(),
            "RUNPOD_ENDPOINT_ID": self.runpod_endpoint_id,
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise ValueError("missing settings required in production: " + ", ".join(missing))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings, read from the environment once per process."""
    return Settings()
