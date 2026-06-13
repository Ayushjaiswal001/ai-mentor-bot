"""Tiny HTTP server: HF Spaces port health check + UptimeRobot keep-alive target."""

import logging
import threading

from fastapi import FastAPI

api = FastAPI(title="AI Mentor Bot", docs_url=None, redoc_url=None)


@api.get("/")
def root() -> dict:
    return {"status": "AI Mentor Bot is alive 🤖"}


@api.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


def start_health_server(port: int) -> None:
    """Run uvicorn in a daemon thread so it never blocks the bot's polling loop."""

    log = logging.getLogger(__name__)

    def _run() -> None:
        import uvicorn

        try:
            log.info("health server binding on 0.0.0.0:%s", port)
            config = uvicorn.Config(api, host="0.0.0.0", port=port, log_level="info")
            server = uvicorn.Server(config)
            server.install_signal_handlers = lambda: None  # safe in a non-main thread
            server.run()
        except Exception:
            log.exception("health server failed to start")

    threading.Thread(target=_run, daemon=True, name="health-server").start()
