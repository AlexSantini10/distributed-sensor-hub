"""Launch a distributed sensor-hub node process.

Responsibilities:
    - Initialize bootstrap logging and process-wide exception hooks.
    - Load environment-backed node configuration and logging settings.
    - Construct the runtime application that owns networking, membership,
      sensor ingestion, LWW state replication, gossip-driven peer discovery,
      and the monitoring API.
    - Transfer control to the long-running node lifecycle until shutdown.
"""

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
	"""Start the node runtime from process bootstrap through steady state.

	This function prepares logging, validates configuration, and starts the
	application container that brings up the TCP protocol stack, membership
	bootstrap, sensor event processing, and replicated state dissemination. Once
	started, the node participates in best-effort gossip-style peer discovery and
	last-writer-wins state convergence through the subsystems owned by
	``NodeApplication``.

	Returns:
		None: This function blocks in the application main loop until the process
		shuts down.

	Raises:
		Exception: Propagates configuration, logging, or runtime startup failures
		after recording them through bootstrap or node logging.
	"""
	setup_bootstrap_logging()
	install_global_exception_hooks()

	bootstrap_log = logging.getLogger("bootstrap")
	bootstrap_log.info("Node process starting")

	try:
		config = load_config()
	except Exception:
		bootstrap_log.critical("Failed to load configuration", exc_info=True)
		raise

	clear_log_file_if_requested(config.log_file, config.should_clear_log())

	try:
		setup_logging(config.node_id, config.log_level_name, config.log_file)
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
