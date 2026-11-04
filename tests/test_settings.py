import pytest

from emporio.settings import SettingsError, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr("emporio.settings.load_dotenv", lambda: None)  # ignore the developer's .env
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "STORE_TODAY"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_to_gemini_stable_model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    settings = load_settings()
    assert (settings.provider, settings.model) == ("gemini", "gemini-3.5-flash")


def test_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")
    assert load_settings().model == "gemini-3.8-flash"


def test_missing_key_is_a_clear_error():
    with pytest.raises(SettingsError, match="LLM_API_KEY"):
        load_settings()


def test_invalid_store_today(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("STORE_TODAY", "02/20/2026")
    with pytest.raises(SettingsError, match="YYYY-MM-DD"):
        load_settings()
