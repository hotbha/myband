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


# --- The MIDI window -------------------------------------------------------------
#
# The window a job uses is a *cap* now. `MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS` says how
# much of a recording one job may transcribe and `WorkerTuning.midi_window_for` takes the
# smaller of that and the recording, so the field's name had to change with its meaning.
# The old name still sets the same field, which is the part worth pinning: an operator who
# asked for 30 seconds was asking for a *smaller* window, and silently handing them 120
# would be a surprise in the direction of cost.


def test_the_midi_window_defaults_to_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh install gets 120 seconds, which covers every beta recording but two."""
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.delenv("MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS", raising=False)
    monkeypatch.delenv("MYBAND_WORKER_MIDI_WINDOW_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.worker_midi_max_window_seconds == 120


def test_the_legacy_window_name_still_sets_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """`MYBAND_WORKER_MIDI_WINDOW_SECONDS` was the name before the field was a cap.

    Its old meaning was "transcribe this many seconds of every recording", which for any
    song at least that long is exactly what a cap of that size still does.
    """
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.setenv("MYBAND_WORKER_MIDI_WINDOW_SECONDS", "30")
    monkeypatch.delenv("MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.worker_midi_max_window_seconds == 30


def test_the_current_window_name_wins_over_the_legacy_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both set is the migration window: the name an operator just wrote is the one read."""
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.setenv("MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS", "90")
    monkeypatch.setenv("MYBAND_WORKER_MIDI_WINDOW_SECONDS", "30")

    settings = Settings(_env_file=None)

    assert settings.worker_midi_max_window_seconds == 90


@pytest.mark.parametrize("value", ["4", "601"])
def test_the_window_is_bounded_at_both_ends(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """`ge=5, le=600`: a window that cannot transcribe anything, or that outlives the lease."""
    monkeypatch.setenv("MYBAND_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_URL)
    monkeypatch.setenv("MYBAND_WORKER_MIDI_MAX_WINDOW_SECONDS", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
