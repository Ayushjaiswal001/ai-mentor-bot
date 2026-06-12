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

    def _run() -> None:
        import uvicorn

        try:
            uvicorn.run(api, host="0.0.0.0", port=port, log_level="warning")
        except Exception:
            logging.getLogger(__name__).exception("health server failed to start")

    threading.Thread(target=_run, daemon=True, name="health-server").start()
