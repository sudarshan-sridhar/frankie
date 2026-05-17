"""Structured logging setup.

Emits JSON-line logs to data/logs/claw.log and human-readable logs to stderr.
All modules obtain loggers via structlog.get_logger(__name__); never use print.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from frankie.config import get_settings

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor

_state: dict[str, bool] = {"configured": False}


def configure_logging() -> None:
    """Configure stdlib + structlog. Idempotent.

    Stderr gets a human-friendly renderer. data/logs/claw.log gets JSON lines.
    """
    if _state["configured"]:
        return

    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path: Path = settings.logs_dir / "claw.log"
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    human_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            _drop_extras,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )
    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            _drop_extras,
            structlog.processors.JSONRenderer(),
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(human_formatter)
    root.addHandler(stderr_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(json_formatter)
    root.addHandler(file_handler)

    _state["configured"] = True


def _drop_extras(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Drop _record and _from_structlog before rendering."""
    event_dict.pop("_record", None)
    event_dict.pop("_from_structlog", None)
    return event_dict
