import logging
import re
import sys

import structlog

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s\-().]{7,}\d)(?!\d)"
)
_TOKEN_RE = re.compile(
    r"\b(?:sk|pk|ghp|gho|ghs|hf|xox[abps]|AIza|Bearer)[_\-]?[A-Za-z0-9]{16,}\b"
)
_HIGH_ENTROPY_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


def _redact_string(value: str) -> str:
    if not value or not isinstance(value, str):
        return value
    redacted = _EMAIL_RE.sub("[email]", value)
    redacted = _TOKEN_RE.sub("[token]", redacted)
    redacted = _PHONE_RE.sub("[phone]", redacted)
    # Anything left that looks like a high-entropy secret (long opaque blob)
    redacted = _HIGH_ENTROPY_RE.sub("[redacted]", redacted)
    return redacted


def _redact_pii(_logger, _name, event_dict):
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _redact_string(value)
        elif isinstance(value, list):
            event_dict[key] = [
                _redact_string(item) if isinstance(item, str) else item
                for item in value
            ]
    return event_dict


def configure_logging(log_level: str, *, json_logs: bool) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
        force=True,
    )
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_pii,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
