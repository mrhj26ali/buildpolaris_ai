"""Structured JSON logging (NFR-OBS.1) â€” every log line can carry a
trace_id that follows a request across PWA -> BFF -> AI sidecar so a
single user-reported issue is traceable end-to-end without timestamp
guesswork (ARCH Â§4.2 "Correlation").
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import get_settings
from app.observability.tracing import trace_id_var


def _add_trace_id(logger, method_name, event_dict):
    trace_id = trace_id_var.get(None)
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def configure_logging() -> None:
    settings = get_settings().observability
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level, force=True
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_trace_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
