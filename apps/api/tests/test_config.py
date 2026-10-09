"""Settings: the two rules that are easy to get wrong.

``_env_file=None`` makes these tests independent of whatever ``apps/api/.env``
holds on the machine running them.
"""

import pytest
from app.core.config import Settings
from pydantic import ValidationError

DEVELOPMENT_URL = "postgresql://postgres:postgres@localhost:5432/postgres"


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """No connection string, no service - it is the one setting with no default."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_every_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """A production boot without R2 or RunPod keys fails here, not on first use."""
    monkeypatch.setenv("MYBAND_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    message = str(error.value)
    assert "R2_ACCESS_KEY_ID" in message
    assert "RUNPOD_API_KEY" in message


def test_development_boots_without_third_party_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)

    settings = Settings(_env_file=None)

    assert settings.is_production is False
    assert settings.cors_origin_list == ["http://localhost:3000"]
