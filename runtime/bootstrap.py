"""Process bootstrap utilities."""

import logging
import os
import sys
import threading
from typing import Optional

from dotenv import load_dotenv


def setup_bootstrap_logging() -> None:
	"""Initialize early process logging."""
	logging.basicConfig(
		level=logging.DEBUG,
		format="%(asctime)s | %(levelname)s | BOOTSTRAP | %(message)s",
		stream=sys.stderr,
	)


def _global_exception_hook(exc_type, exc, tb) -> None:
	"""Log unhandled main-thread exceptions."""
	logging.getLogger("bootstrap").critical(
		"UNHANDLED EXCEPTION",
		exc_info=(exc_type, exc, tb),
	)


def _thread_exception_hook(args) -> None:
	"""Log unhandled worker-thread exceptions."""
	logging.getLogger("bootstrap").critical(
		f"UNHANDLED THREAD EXCEPTION in thread {args.thread.name}",
		exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
	)


def install_global_exception_hooks() -> None:
	"""Install process-wide exception hooks and load environment."""
	load_dotenv()
	sys.excepthook = _global_exception_hook
	threading.excepthook = _thread_exception_hook


def clear_log_file_if_requested(log_file: Optional[str]) -> None:
	"""Clear the configured log file when requested by environment."""
	clear_log = os.getenv("CLEAR_LOG", "false").lower() == "true"
	if not clear_log or not log_file:
		return

	try:
		with open(log_file, "w", encoding="utf-8"):
			pass
	except OSError:
		logging.getLogger("bootstrap").error(
			f"Failed to clear log file {log_file}",
			exc_info=True,
		)