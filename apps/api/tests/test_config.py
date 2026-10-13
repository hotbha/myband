"""Settings: the rules that are easy to get wrong.

``_env_file=None`` makes these tests independent of whatever ``apps/api/.env``
holds on the machine running them.
"""

import pytest
from app.core.config import Settings
from pydantic import ValidationError

DEVELOPMENT_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

# What a production boot is supposed to demand: the credentials the running code
# reads. RunPod's are deliberately not among them - see the last two tests.
PRODUCTION_SECRETS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "R2_ACCOUNT_ID": "account-id",
    "R2_ACCESS_KEY_ID": "access-key-id",
    "R2_SECRET_ACCESS_KEY": "secret-access-key",
}


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """No connection string, no service - it is the one setting with no default."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_the_credentials_it_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production boot without R2 keys fails here, not on the first upload."""
    monkeypatch.setenv("MYBAND_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    for name, value in PRODUCTION_SECRETS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    message = str(error.value)
    assert "R2_ACCESS_KEY_ID" in message
    assert "RUNPOD_API_KEY" not in message


def test_production_boots_without_runpod_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing calls RunPod yet, so a production boot must not ask for its keys.

    The dispatcher is the first thing that will read them: the commit that lands it
    puts them back in ``_require_production_secrets`` and flips this test.
    """
    monkeypatch.setenv("MYBAND_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    for name, value in PRODUCTION_SECRETS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.delenv("RUNPOD_ENDPOINT_ID", raising=False)

    settings = Settings(_env_file=None)

    assert settings.is_production is True
    assert settings.runpod_api_key.get_secret_value() == ""
    assert settings.runpod_endpoint_id == ""


def test_development_boots_without_third_party_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)

    settings = Settings(_env_file=None)

    assert settings.is_production is False
    assert settings.cors_origin_list == ["http://localhost:3000"]
