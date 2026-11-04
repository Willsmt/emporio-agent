"""Runtime settings loaded from environment variables (.env)."""
import os
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

STORE_TIMEZONE = ZoneInfo("America/Campo_Grande")
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash", "openai": "gpt-6-luna"}


class SettingsError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str
    store_today: date | None = None
    min_interval_seconds: float = 0.0
    demo_mode: bool = False

    def now(self) -> datetime:
        current = datetime.now(STORE_TIMEZONE)
        if self.store_today:
            return current.replace(year=self.store_today.year, month=self.store_today.month, day=self.store_today.day)
        return current


def load_settings() -> Settings:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise SettingsError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got '{provider}'")

    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise SettingsError("LLM_API_KEY is not set. Copy .env.example to .env and fill it in.")

    raw_today = os.getenv("STORE_TODAY", "").strip()
    try:
        store_today = date.fromisoformat(raw_today) if raw_today else None
    except ValueError as exc:
        raise SettingsError(f"STORE_TODAY must be YYYY-MM-DD, got '{raw_today}'") from exc

    raw_interval = os.getenv("LLM_MIN_INTERVAL_SECONDS", "").strip()
    try:
        min_interval = float(raw_interval) if raw_interval else 0.0
    except ValueError as exc:
        raise SettingsError(f"LLM_MIN_INTERVAL_SECONDS must be a number, got '{raw_interval}'") from exc

    return Settings(
        provider=provider,
        model=os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS[provider],
        api_key=api_key,
        store_today=store_today,
        min_interval_seconds=min_interval,
        demo_mode=os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes"},
    )


def parse_trusted_proxy_hops(raw: str | None) -> int:
    """TRUSTED_PROXY_HOPS: number of reverse proxies in front of the web app (0 = none, the default)."""
    value = (raw or "").strip()
    if not value:
        return 0
    try:
        hops = int(value)
    except ValueError:
        hops = -1
    if hops < 0:
        raise SettingsError(f"TRUSTED_PROXY_HOPS must be an integer >= 0, got '{value}'")
    return hops
