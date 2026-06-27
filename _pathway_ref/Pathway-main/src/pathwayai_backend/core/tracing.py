import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pathwayai_backend.config import Settings

logger = structlog.get_logger(__name__)


class TraceRecorder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def record(self, event: str, **data: Any) -> None:
        logger.info(event, **data)
        if self.settings.langsmith_tracing:
            return
        path = Path(self.settings.local_trace_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                **data,
            }
            with path.open("a", encoding="utf-8") as trace_file:
                trace_file.write(json.dumps(payload, default=str) + "\n")
        except OSError:
            logger.warning("local_trace_write_failed", path=str(path), exc_info=True)
