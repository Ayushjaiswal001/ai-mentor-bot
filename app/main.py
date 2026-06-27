"""Entry point: python -m app.main

Runs the Telegram bot (long polling) and the health/keep-alive HTTP server in a single
asyncio event loop. Single-loop design avoids cross-thread loop issues in containers.
"""

import asyncio
import logging
import os
from pathlib import Path

from app.api.health import make_server, set_bot_app
from app.bot.app import build_application, setup_application

logger = logging.getLogger("app.main")


async def _bootstrap():
    """Build + initialize + start polling. Network-touchy — caller retries on failure."""
    app = build_application()
    await app.initialize()
    await setup_application(app)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    return app


async def amain() -> None:
    Path("data").mkdir(exist_ok=True)
    # NOTE: app/diagnostics.run_probe() exists to test egress on a new host — call it
    # from here temporarily if Telegram connectivity is ever in doubt again.

    # Open the health port immediately (in parallel) so the host's health check never
    # waits on bot bootstrap. The server task runs until the process is killed.
    server = make_server(int(os.environ.get("PORT", "7860")))
    server_task = asyncio.create_task(server.serve())

    app = None
    for attempt in range(1, 9):
        try:
            app = await _bootstrap()
            break
        except Exception as e:  # transient TimedOut/NetworkError on cold-start, Neon waking, etc.
            logger.warning("bootstrap attempt %s failed: %r", attempt, e)
            if app is not None:
                try:
                    await app.shutdown()
                except Exception:
                    pass
                app = None
            await asyncio.sleep(min(3 * attempt, 20))
    if app is None:
        server.should_exit = True
        raise RuntimeError("bot failed to start after retries")
    logger.info("bot polling started")
    set_bot_app(app)  # /healthz now reports 503 if polling dies → host restarts the container

    try:
        await server_task  # blocks until the process is signalled/killed
    finally:
        logger.info("shutting down")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(amain())


if __name__ == "__main__":
    main()
