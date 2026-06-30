"""Application logging configuration.

Provides a single ``configure_logging()`` entry point (idempotent) and a
``get_logger()`` helper. Each pipeline run gets a short run id so logs from
concurrent sessions can be correlated.
"""

from __future__ import annotations

import logging
import os
import uuid

from config import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    """Configure root logging once. Safe to call repeatedly."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = get_settings().log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root = logging.getLogger()
    # Avoid duplicate handlers when Streamlit re-runs the script.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers unless we're explicitly debugging.
    if level > logging.DEBUG:
        for noisy in ("httpx", "httpcore", "urllib3", "openai"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def new_run_id() -> str:
    """Short id to tag a single pipeline run across log lines."""
    # uuid4 is fine here; this is a correlation id, not a security token.
    return os.environ.get("RUN_ID") or uuid.uuid4().hex[:8]
