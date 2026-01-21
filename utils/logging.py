import logging
import os


def setup_logging(node_id: str, level: str, log_file: str) -> None:
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
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


class NodeLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        extra["node_id"] = self.extra["node_id"]
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, node_id: str) -> NodeLogger:
    logger = logging.getLogger(name)
    return NodeLogger(logger, {"node_id": node_id})
