"""Validate logging setup behavior."""

import logging
from pathlib import Path
import uuid

from utils.config import LogLevel
from utils.logging import DEMO_LEVEL_NUM, demo_event, get_logger, setup_logging


def test_setup_logging_uses_loglevel_enum() -> None:
    """Assert that logging setup accepts and applies ``LogLevel`` values."""
    tmp_dir = Path(".codex-tmp") / "test-logging"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_dir / f"test-setup-logging-enum-{uuid.uuid4().hex}.log"
    if log_file.exists():
        log_file.unlink()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    try:
        setup_logging("node-1", LogLevel.DEBUG, str(log_file))
        assert root.level == logging.DEBUG

        log = get_logger("tests.utils.test_logging", "node-1")
        log.info("hello")

        content = log_file.read_text(encoding="utf-8")
        assert "INFO" in content
        assert "node-1" in content
        assert "hello" in content
    finally:
        for handler in list(root.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        if log_file.exists():
            log_file.unlink()


def test_logger_demo_emits_and_suppresses_info_at_demo_level() -> None:
    """Assert ``logger.demo`` emits while INFO is suppressed at ``DEMO`` root level."""
    tmp_dir = Path(".codex-tmp") / "test-logging"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_dir / f"test-demo-level-{uuid.uuid4().hex}.log"
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    try:
        setup_logging("node-x", LogLevel.DEMO, str(log_file))
        assert root.level == DEMO_LEVEL_NUM
        log = get_logger("tests.utils.test_logging.demo", "node-x")
        log.info("info-noise")
        log.demo("demo-signal")

        content = log_file.read_text(encoding="utf-8")
        assert "demo-signal" in content
        assert "info-noise" not in content
    finally:
        for handler in list(root.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        if log_file.exists():
            log_file.unlink()


def test_demo_event_format_prefix_and_key_value_pairs() -> None:
    """Assert demo events use strict ``[DEMO] EVENT key=value`` formatting."""
    tmp_dir = Path(".codex-tmp") / "test-logging"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_dir / f"test-demo-format-{uuid.uuid4().hex}.log"
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    try:
        setup_logging("node-y", LogLevel.DEMO, str(log_file))
        log = get_logger("tests.utils.test_logging.format", "node-y")
        demo_event(log, "JOIN_REQUEST", **{"from": "node-a"})
        content = log_file.read_text(encoding="utf-8")
        assert "[DEMO] JOIN_REQUEST from=node-a" in content
    finally:
        for handler in list(root.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        if log_file.exists():
            log_file.unlink()
