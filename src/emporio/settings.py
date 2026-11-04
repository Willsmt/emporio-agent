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

    return Settings(
        provider=provider,
        model=os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS[provider],
        api_key=api_key,
        store_today=store_today,
    )
