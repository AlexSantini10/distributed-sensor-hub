"""Validate logging setup behavior."""

import logging
from pathlib import Path
import uuid

from utils.config import LogLevel
from utils.logging import get_logger, setup_logging


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
