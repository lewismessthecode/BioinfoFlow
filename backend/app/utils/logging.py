from __future__ import annotations

import logging
import os
import sys
import traceback
from typing import Any

import structlog

from app.config import settings


_MAX_TRACEBACK_FRAMES = 5


def _compact_exc_info(
    logger: Any, method: str, event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that replaces full tracebacks with a compact summary.

    Production-friendly: keeps the exception type, message, and the last N
    frames from application code (skips library frames where possible).
    """
    exc_info = event_dict.pop("exc_info", None)
    if exc_info is True:
        exc_info = sys.exc_info()
    if not exc_info or exc_info[0] is None:
        return event_dict

    exc_type, exc_value, exc_tb = exc_info

    # Extract frames, preferring app code over library internals
    all_frames = traceback.extract_tb(exc_tb)
    app_frames = [f for f in all_frames if "/app/" in f.filename]
    frames = app_frames[-_MAX_TRACEBACK_FRAMES:] if app_frames else all_frames[-_MAX_TRACEBACK_FRAMES:]

    formatted = [
        f"  {f.filename.split('/app/')[-1] if '/app/' in f.filename else f.filename}:{f.lineno} in {f.name}"
        for f in frames
    ]

    exc_name = exc_type.__name__ if exc_type else "Exception"
    event_dict["exception"] = f"{exc_name}: {exc_value}"
    if formatted:
        event_dict["traceback"] = formatted

    return event_dict


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        # Suppress uvicorn's duplicate full-traceback on handled exceptions.
        # Our FastAPI exception handlers already log a structured summary;
        # uvicorn's ASGI-level traceback is redundant and very long.
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if debug:
        # Full traceback in dev for easy debugging
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # Compact traceback in production: last 3 frames only
        processors.append(_compact_exc_info)
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configure_langsmith()


def _configure_langsmith() -> None:
    if not settings.langsmith_tracing:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    if settings.langsmith_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langsmith_endpoint)


def bind_request_id(request_id: str | None) -> None:
    if request_id:
        structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
