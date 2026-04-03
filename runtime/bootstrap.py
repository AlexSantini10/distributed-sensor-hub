"""Prepare process-wide runtime behavior before node startup.

Responsibilities:
    Configure early logging that is available before the main application is
    constructed.
    Install global exception hooks so unexpected failures in the main thread
    and worker threads are surfaced consistently.
    Load environment variables and optionally clear persisted logs for a fresh
    run.
"""

import logging
import os
import sys
import threading
from typing import Optional

from dotenv import load_dotenv


def setup_bootstrap_logging() -> None:
	"""Configure process logging for bootstrap-time diagnostics."""
	logging.basicConfig(
		level=logging.DEBUG,
		format="%(asctime)s | %(levelname)s | BOOTSTRAP | %(message)s",
		stream=sys.stderr,
	)


def _global_exception_hook(exc_type, exc, tb) -> None:
	"""Log an unhandled exception raised on the main thread.

	Args:
		exc_type: Exception class raised by the interpreter.
		exc: Exception instance associated with the failure.
		tb: Traceback object captured at the failure site.
	"""
	logging.getLogger("bootstrap").critical(
		"UNHANDLED EXCEPTION",
		exc_info=(exc_type, exc, tb),
	)


def _thread_exception_hook(args) -> None:
	"""Log an unhandled exception raised by a worker thread.

	Args:
		args: Thread exception payload provided by `threading.excepthook`.
	"""
	logging.getLogger("bootstrap").critical(
		f"UNHANDLED THREAD EXCEPTION in thread {args.thread.name}",
		exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
	)


def install_global_exception_hooks() -> None:
	"""Install process-wide exception hooks and load environment variables.

	This should run before subsystem construction so all threads inherit the
	bootstrap failure-reporting behavior.
	"""
	load_dotenv()
	sys.excepthook = _global_exception_hook
	threading.excepthook = _thread_exception_hook


def clear_log_file_if_requested(log_file: Optional[str]) -> None:
	"""Truncate the configured log file when `CLEAR_LOG=true`.

	Args:
		log_file: Path to the log file to clear, if file logging is enabled.

	Raises:
		No exception is propagated. File-system errors are logged and ignored.
	"""
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
