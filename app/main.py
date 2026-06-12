"""Entry point: python -m app.main  (polling mode)."""

import logging
import os
from pathlib import Path

from app.api.health import start_health_server
from app.bot.app import build_application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    Path("data").mkdir(exist_ok=True)
    start_health_server(port=int(os.environ.get("PORT", "7860")))
    build_application().run_polling()


if __name__ == "__main__":
    main()
