"""Start the web server: python -m emporio.web  (HOST and PORT env vars are honored, e.g. on a host platform)."""
import logging
import os
import sys

import uvicorn

from emporio.agent.factory import build_agent
from emporio.config import DB_PATH, PROCESSED_DIR
from emporio.settings import SettingsError, load_settings
from emporio.tools.db import connect_readonly
from emporio.web.app import create_app
from emporio.web.storefront import build_storefront
from emporio.web.transcripts import TranscriptStore


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        agent = build_agent(settings)
        storefront_conn = connect_readonly(DB_PATH)
    except (SettingsError, FileNotFoundError) as exc:
        print(f"Configuration error: {exc}")
        return 1
    app = create_app(
        agent,
        TranscriptStore(PROCESSED_DIR / "transcripts.db"),
        info={"provider": settings.provider, "model": settings.model},
        demo_mode=settings.demo_mode,
        storefront=lambda: build_storefront(storefront_conn, settings.now()),
    )
    # Behind a platform proxy, set FORWARDED_ALLOW_IPS to the proxy address (or "*") so the rate limit
    # sees each client's real IP from X-Forwarded-For instead of the proxy's.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
