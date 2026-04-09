"""Configure process logging with node-aware context enrichment.

Responsibilities:
    - Install the project's root file handler and formatter.
    - Inject the local node identifier into every emitted log record.
    - Provide logger adapters for components that need structured node context.
"""

import logging
import os
from collections.abc import MutableMapping

from utils.config import LogLevel


def setup_logging(node_id: str, level: LogLevel, log_file: str) -> None:
    """Configure root logging for one node process.

    Args:
        node_id (str): Local node identifier recorded in every log entry.
        level (LogLevel): Root logging level represented by the validated enum.
        log_file (str): File path used for append-only logging output.

    Returns:
        None: This method mutates the root logger configuration.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(node_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level.value)
    root.handlers.clear()
    root.addHandler(handler)


class NodeLogger(logging.LoggerAdapter):
    """Attach the current node identifier to delegated log records.

    Attributes:
        logger (logging.Logger): Wrapped logger used for actual record emission.
        extra (dict[str, object]): Adapter context containing the required ``node_id`` field.
    """

    def process(
        self,
        msg: object,
        kwargs: MutableMapping[str, object],
    ) -> tuple[object, MutableMapping[str, object]]:
        """Inject ``node_id`` into the record extras for downstream formatting.

        Args:
            msg (object): Log message passed through the adapter.
            kwargs (MutableMapping[str, object]): Logging keyword arguments supplied
                by the caller.

        Returns:
            tuple[object, MutableMapping[str, object]]: Message and keyword arguments
                with ``node_id`` attached.
        """
        extra_value = kwargs.get("extra", {})
        extra: dict[str, object]
        if isinstance(extra_value, dict):
            extra = dict(extra_value)
        else:
            extra = {}
        adapter_extra = self.extra
        if adapter_extra is not None and "node_id" in adapter_extra:
            extra["node_id"] = adapter_extra["node_id"]
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, node_id: str) -> NodeLogger:
    """Create a node-aware logger adapter for one component.

    Args:
        name (str): Logger name used to retrieve the underlying logger.
        node_id (str): Local node identifier injected into every record.

    Returns:
        NodeLogger: Adapter that enriches records with node context.
    """
    logger = logging.getLogger(name)
    return NodeLogger(logger, {"node_id": node_id})
