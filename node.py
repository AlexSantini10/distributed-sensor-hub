"""Node process entrypoint."""

import logging

from runtime.application import NodeApplication
from runtime.bootstrap import (
	clear_log_file_if_requested,
	install_global_exception_hooks,
	setup_bootstrap_logging,
)

from utils.config import load_config
from utils.logging import get_logger, setup_logging


def main() -> None:
	"""Start the node process."""
	setup_bootstrap_logging()
	install_global_exception_hooks()

	bootstrap_log = logging.getLogger("bootstrap")
	bootstrap_log.info("Node process starting")

	try:
		config = load_config()
	except Exception:
		bootstrap_log.critical("Failed to load configuration", exc_info=True)
		raise

	clear_log_file_if_requested(config.log_file)

	try:
		setup_logging(config.node_id, config.log_level, config.log_file)
	except Exception:
		bootstrap_log.critical("Failed to setup logging", exc_info=True)
		raise

	log = get_logger(__name__, config.node_id)
	log.info("Full logging initialized")

	app = NodeApplication(config=config, log=log)
	app.start()
	app.run_forever()


if __name__ == "__main__":
	main()