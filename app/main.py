"""Entry point: python -m app.main

Runs the Telegram bot (long polling) and the health/keep-alive HTTP server in a single
asyncio event loop. Single-loop design avoids cross-thread loop issues in containers.
"""

import asyncio
import logging
import os
from pathlib import Path

from app.api.health import make_server
from app.bot.app import build_application, setup_application

logger = logging.getLogger("app.main")


async def amain() -> None:
    Path("data").mkdir(exist_ok=True)
    app = build_application()
    await app.initialize()
    await setup_application(app)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("bot polling started")

    server = make_server(int(os.environ.get("PORT", "7860")))
    try:
        await server.serve()  # blocks until the process is signalled/killed
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
