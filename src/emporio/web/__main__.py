"""Start the web server: python -m emporio.web  (HOST and PORT env vars are honored, e.g. on a host platform)."""
import logging
import os
import sys

import uvicorn

from emporio.agent.factory import build_agent
from emporio.config import PROCESSED_DIR
from emporio.settings import SettingsError, load_settings
from emporio.web.app import create_app
from emporio.web.transcripts import TranscriptStore


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        agent = build_agent(settings)
    except (SettingsError, FileNotFoundError) as exc:
        print(f"Configuration error: {exc}")
        return 1
    app = create_app(
        agent,
        TranscriptStore(PROCESSED_DIR / "transcripts.db"),
        info={"provider": settings.provider, "model": settings.model},
    )
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
