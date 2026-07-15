"""Tests for the logger configuration."""
import logging

from src.utils.logger import ROOT_LOGGER_NAME, get_logger


def test_get_logger_returns_child():
    log = get_logger("scrapers.immunefi")
    assert log.name == f"{ROOT_LOGGER_NAME}.scrapers.immunefi"


def test_get_logger_idempotent():
    log1 = get_logger("test_module")
    log2 = get_logger("test_module")
    assert log1 is log2


def test_root_logger_has_handler():
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert root.handlers, "root bounty logger should have at least one handler"


def test_logger_emits_record():
    log = get_logger("test_emit")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    capture = _Capture(level=logging.INFO)
    log.addHandler(capture)
    try:
        log.info("hello %s", "world")
    finally:
        log.removeHandler(capture)
    assert "hello world" in records
