"""
Centralised logging configuration.

Every module does:

    from src.utils.logger import get_logger
    log = get_logger("scrapers.immunefi")
    log.info("Found %d bounties", n)

Configured once on import of this module. Controlled by env vars:
    LOG_LEVEL   default INFO
    LOG_FORMAT  default rich  (rich | plain | json)
"""
from __future__ import annotations

import logging
import os
import sys

_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_FORMAT = os.getenv("LOG_FORMAT", "rich").lower()
_LEVEL_NUM = getattr(logging, _LEVEL, logging.INFO)
ROOT_LOGGER_NAME = "bounty"


class _OneLineFormatter(logging.Formatter):
    """Force every log message onto a single line (great for CI logs)."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return " ".join(msg.splitlines())


def _build_handler() -> logging.Handler:
    if _FORMAT == "json":
        import json
        import time

        class _JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                return json.dumps(payload, default=str)

        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_JsonFormatter())
        return h

    if _FORMAT == "rich":
        try:
            from rich.logging import RichHandler

            h = RichHandler(
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
            )
            return h
        except ImportError:
            pass

    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(
        _OneLineFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    return h


def _configure_root() -> logging.Logger:
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if root.handlers:
        return root
    root.setLevel(_LEVEL_NUM)
    root.addHandler(_build_handler())
    root.propagate = False
    return root


_configure_root()


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the project root."""
    if name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def silence_noisy_libs() -> None:
    """Quiet down chatty third-party loggers."""
    for noisy in ("urllib3", "playwright", "asyncio", "chardet", "PIL", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
