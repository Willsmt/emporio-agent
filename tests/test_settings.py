import pytest

from emporio.settings import SettingsError, load_settings, parse_trusted_proxy_hops


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr("emporio.settings.load_dotenv", lambda: None)  # ignore the developer's .env
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "STORE_TODAY", "LLM_MIN_INTERVAL_SECONDS", "DEMO_MODE"):
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


def test_rate_limit_setting(monkeypatch):
    from emporio.agent.providers import create_provider
    from emporio.agent.providers.rate_limit import RateLimitedProvider

    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MIN_INTERVAL_SECONDS", "13")
    settings = load_settings()
    assert settings.min_interval_seconds == 13.0
    assert isinstance(create_provider(settings), RateLimitedProvider)


@pytest.mark.parametrize("value, expected", [("", False), ("false", False), ("true", True), ("1", True)])
def test_demo_mode_is_off_unless_enabled(monkeypatch, value, expected):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DEMO_MODE", value)
    assert load_settings().demo_mode is expected


@pytest.mark.parametrize("raw, expected", [(None, 0), ("", 0), (" 0 ", 0), ("1", 1), ("2", 2)])
def test_trusted_proxy_hops(raw, expected):
    assert parse_trusted_proxy_hops(raw) == expected


@pytest.mark.parametrize("raw", ["-1", "one", "1.5", "*"])
def test_invalid_trusted_proxy_hops_is_a_configuration_error(raw):
    with pytest.raises(SettingsError, match="TRUSTED_PROXY_HOPS"):
        parse_trusted_proxy_hops(raw)
