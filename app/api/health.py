"""Tiny HTTP server: HF Spaces port health check + keep-alive ping target.

Runs as a coroutine in the bot's own event loop (see app/main.py) — no extra thread.
"""

from fastapi import FastAPI

api = FastAPI(title="AI Mentor Bot", docs_url=None, redoc_url=None)


@api.get("/")
def root() -> dict:
    return {"status": "AI Mentor Bot is alive 🤖"}


@api.get("/healthz")
def healthz() -> dict:
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
