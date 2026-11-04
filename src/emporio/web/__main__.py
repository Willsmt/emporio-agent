"""Start the web server: python -m emporio.web  (HOST and PORT env vars are honored, e.g. on a host platform)."""
import logging
import os
import sys

import uvicorn

from emporio.agent.factory import build_agent
from emporio.config import DB_PATH, PROCESSED_DIR
from emporio.settings import SettingsError, load_settings, parse_trusted_proxy_hops
from emporio.tools.db import connect_readonly
from emporio.web.app import create_app
from emporio.web.storefront import build_storefront
from emporio.web.transcripts import TranscriptStore


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        trusted_proxy_hops = parse_trusted_proxy_hops(os.getenv("TRUSTED_PROXY_HOPS"))
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
        trusted_proxy_hops=trusted_proxy_hops,
    )
    # Proxy headers are not applied by uvicorn: the app picks the client IP itself from TRUSTED_PROXY_HOPS
    # (see web.app.client_ip), so a client cannot choose its own rate-limit key with a forged X-Forwarded-For.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
