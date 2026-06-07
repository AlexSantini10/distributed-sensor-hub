"""Prepare process-wide behavior required before node startup.

Responsibilities:
    - Configure early logging that is available before the application exists.
    - Install global exception hooks for main-thread and worker-thread failures.
    - Load environment variables and optionally clear persisted bootstrap logs.
"""

import logging
import sys
import threading
from types import TracebackType


def setup_bootstrap_logging() -> None:
    """Configure process logging for bootstrap-time diagnostics.

    Returns:
        None: This function installs bootstrap logging configuration.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | BOOTSTRAP | %(message)s",
        stream=sys.stderr,
    )


def _global_exception_hook(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """Log an unhandled exception raised on the main thread.

    Args:
        exc_type (type[BaseException]): Exception class raised by the interpreter.
        exc (BaseException): Exception instance associated with the failure.
        tb (TracebackType | None): Traceback object captured at the failure site.

    Returns:
        None: This hook records the failure through bootstrap logging.
    """
    logging.getLogger("bootstrap").critical(
        "UNHANDLED EXCEPTION",
        exc_info=(exc_type, exc, tb),
    )


def _thread_exception_hook(args: threading.ExceptHookArgs) -> None:
    """Log an unhandled exception raised by a worker thread.

    Args:
        args (threading.ExceptHookArgs): Thread exception payload provided by
            ``threading.excepthook``.

    Returns:
        None: This hook records the failure through bootstrap logging.
    """
    thread_name = args.thread.name if args.thread is not None else "<unknown>"
    if args.exc_value is None:
        logging.getLogger("bootstrap").critical(
            f"UNHANDLED THREAD EXCEPTION in thread {thread_name}"
        )
        return

    logging.getLogger("bootstrap").critical(
        f"UNHANDLED THREAD EXCEPTION in thread {thread_name}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def install_global_exception_hooks() -> None:
    """Install process-wide exception hooks.

    This should run before subsystem construction so all threads inherit the
    bootstrap failure-reporting behavior.

    Returns:
        None: This function installs exception hooks for main and worker threads.
    """
    sys.excepthook = _global_exception_hook
    threading.excepthook = _thread_exception_hook


def clear_log_file_if_requested(log_file: str | None, clear_log: bool) -> None:
    """Truncate the configured log file when requested by configuration.

    Args:
        log_file (str | None): Path to the log file to clear, if file logging is enabled.
        clear_log (bool): Whether startup should truncate the configured log file.

    Returns:
        None: This function truncates the configured log file when requested.
    """
    if not clear_log or log_file is None or log_file == "":
        return

    try:
        with open(log_file, "w", encoding="utf-8"):
            pass
    except OSError:
        logging.getLogger("bootstrap").error(
            f"Failed to clear log file {log_file}",
            exc_info=True,
        )
