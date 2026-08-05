"""Structured logging configuration."""
from __future__ import annotations

import logging
import re
import sys

import structlog

_REDACT_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token|key|smtp_pass)[=:\"'\s]+\S+"),
]


def _redact_processor(
    _logger: object, _method: str, event_dict: dict
) -> dict:
    for k in list(event_dict.keys()):
        if re.search(r"(?i)(password|passwd|secret|token|key|smtp_pass)", k):
            event_dict[k] = "***REDACTED***"
    msg = event_dict.get("event", "")
    if isinstance(msg, str):
        for pat in _REDACT_PATTERNS:
            msg = pat.sub(r"\1=***REDACTED***", msg)
        event_dict["event"] = msg
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    # Silence noisy third-party loggers
    for noisy in ("aiogram", "aiohttp", "asyncio", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))
