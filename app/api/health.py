"""Tiny HTTP server: HF Spaces port health check + keep-alive ping target.

Runs as a coroutine in the bot's own event loop (see app/main.py) — no extra thread.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

api = FastAPI(title="AI Mentor Bot", docs_url=None, redoc_url=None)


def set_bot_app(app) -> None:
    """Let /healthz report live polling state (called from main once polling starts)."""
    api.state.bot_app = app


@api.get("/")
def root() -> dict:
    return {"status": "AI Mentor Bot is alive 🤖"}


@api.get("/healthz")
def healthz():
    app = getattr(api.state, "bot_app", None)
    if app is None or getattr(app, "updater", None) is None or not app.updater.running:
        return JSONResponse({"ok": False}, status_code=503)
    return {"ok": True}


def make_server(port: int):
    """A uvicorn Server that runs inside an existing loop (signal handlers disabled)."""
    import uvicorn

    config = uvicorn.Config(
        api, host="0.0.0.0", port=port, log_level="info", log_config=None
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    return server
