"""Coordinate node startup, steady-state execution, and shutdown.

Responsibilities:
    - Start state processing before any network or sensor input can arrive.
    - Assemble networking, membership, publication, and monitoring subsystems.
    - Stop subsystems in reverse dependency order during process shutdown.
"""

from __future__ import annotations

import threading
import time

from networking.tcp_client import Peer as TcpPeer
from networking.tcp_client import TcpClient
from networking.tcp_server import TcpServer
from runtime.networking import (
    bootstrap_membership,
    seed_peer_table,
    setup_node_networking,
)
from membership.peer_table import PeerTable
from sensors.sensor_manager import SensorManager
from state.events import SensorEventQueue
from state.node_state_worker import NodeStateWorker
from state.sensor_update_publisher import SensorUpdatePublisher
from utils.config import Config
from utils.typing import LoggerLike
from webapi.http_api import WebAPIServer


class NodeApplication:
    """Manage the lifecycle of a distributed sensor-hub node.

    Attributes:
        config (Config): Runtime configuration for node identity, bind address, and peers.
        log (LoggerLike): Logger used for lifecycle and failure reporting.
        sensor_event_queue (SensorEventQueue): Queue that transfers sensor events into state processing.
        state_worker (NodeStateWorker | None): Background worker that owns authoritative local state.
        client (TcpClient | None): Outbound TCP client used to send protocol messages.
        server (TcpServer | None): Inbound TCP server that accepts protocol messages.
        peer_table (PeerTable | None): Membership view shared with gossip and publication flows.
        sensor_manager (SensorManager | None): Manager for local sensor producers.
        publisher (SensorUpdatePublisher | None): Publisher that forwards local state changes to peers.
        web_api (WebAPIServer | None): HTTP server exposing state snapshots for monitoring.
        bootstrap_peers (list[TcpPeer]): Configured peers contacted during initial membership join.
    """

    def __init__(
        self,
        config: Config,
        log: LoggerLike,
    ) -> None:
        """Initialize the runtime container.

        Args:
            config (Config): Runtime configuration object consumed by startup helpers.
            log (LoggerLike): Logger used by the application and child components.

        Returns:
            None: This initializer stores runtime dependencies without starting them.
        """
        self.config = config
        self.log = log

        self.sensor_event_queue = SensorEventQueue()
        self.state_worker: NodeStateWorker | None = None
        self.client: TcpClient | None = None
        self.server: TcpServer | None = None
        self.peer_table: PeerTable | None = None
        self.sensor_manager: SensorManager | None = None
        self.publisher: SensorUpdatePublisher | None = None
        self.web_api: WebAPIServer | None = None
        self.bootstrap_peers: list[TcpPeer] = []
        self._lifecycle_lock = threading.Lock()
        self._stopped = False

    def start(self) -> None:
        """Start all node subsystems in dependency order.

        The sequence ensures that state reception is available before networking,
        that membership bootstrap happens before sensor publication, and that the
        monitoring API observes a fully initialized node.

        Returns:
            None: This method starts the node subsystems in dependency order.
        """
        try:
            self._start_state()
            self._start_networking()
            self._bootstrap_membership()
            self._start_sensors()
            self._start_web_api()
        except Exception:
            self.stop()
            raise

    def run_forever(self) -> None:
        """Keep the process alive until interruption or unrecoverable failure.

        Returns:
            None: This method blocks until shutdown is requested or a fatal error occurs.
        """
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.log.info("Node shutting down (KeyboardInterrupt)")
        except Exception:
            self.log.critical("Unhandled exception in main loop", exc_info=True)
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop all node subsystems in reverse dependency order.

        This method is best-effort. Each subsystem is asked to stop even if an
        earlier shutdown step fails.

        Returns:
            None: This method stops all started subsystems.
        """
        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True

        self.log.info("Node cleanup started")

        if self.publisher is not None:
            try:
                self.publisher.stop()
            except Exception:
                self.log.error("Error while stopping publisher", exc_info=True)

        if self.sensor_manager is not None:
            try:
                self.sensor_manager.stop_all()
            except Exception:
                self.log.error("Error while stopping sensors", exc_info=True)

        if self.web_api is not None:
            try:
                self.web_api.stop()
            except Exception:
                self.log.error("Error while stopping WebAPI", exc_info=True)

        if self.state_worker is not None:
            try:
                self.state_worker.stop()
            except Exception:
                self.log.error("Error while stopping state worker", exc_info=True)

        if self.server is not None or self.client is not None:
            try:
                if self.server is not None:
                    self.server.stop()
                if self.client is not None:
                    self.client.stop()
            except Exception:
                self.log.error("Error while stopping networking", exc_info=True)

        self.log.info("Node shutdown complete")

    def _start_state(self) -> None:
        """Start the state worker before any network or sensor input begins.

        Returns:
            None: This method creates and starts the local state worker.
        """
        self.state_worker = NodeStateWorker(
            node_id=self.config.node_id,
            event_queue=self.sensor_event_queue,
            log=self.log,
        )
        self.state_worker.start()
        self.log.info("State worker started")

    def _start_networking(self) -> None:
        """Create the protocol stack and start inbound networking.

        Returns:
            None: This method initializes protocol routing and starts inbound transport.

        Raises:
            Exception: Propagates setup or server startup failures so startup can
                abort atomically.
        """
        assert self.state_worker is not None

        networking = setup_node_networking(
            config=self.config,
            log=self.log,
            state_worker=self.state_worker,
            tcp_server_cls=TcpServer,
        )

        self.client = networking.client
        self.server = networking.server
        self.peer_table = networking.peer_table
        self.bootstrap_peers = networking.bootstrap_peers

        try:
            self.server.start()
        except Exception:
            self.log.critical("Failed to start TCP server", exc_info=True)
            raise

        self.log.info(f"Node listening on {self.config.host}:{self.config.port}")

    def _bootstrap_membership(self) -> None:
        """Seed the membership view and send initial ``JOIN_REQUEST`` messages.

        Bootstrap peers are inserted optimistically so outbound gossip and update
        routing have an initial target set. The explicit join requests establish
        the node's advertised endpoint and begin membership convergence.

        Returns:
            None: This method seeds membership and emits initial join messages.
        """
        assert self.peer_table is not None
        assert self.client is not None

        seed_peer_table(
            peer_table=self.peer_table,
            bootstrap_peers=self.bootstrap_peers,
            log=self.log,
        )

        if not self.bootstrap_peers:
            self.log.info("No bootstrap peers configured")
            return

        bootstrap_membership(
            self_node_id=self.config.node_id,
            host=self.config.host,
            port=self.config.port,
            peers=self.bootstrap_peers,
            send=self.client.send_json,
            log=self.log,
        )

    def _start_sensors(self) -> None:
        """Start local sensors and publish their updates to the cluster.

        Returns:
            None: This method starts local sensors and the replication publisher.

        Raises:
            Exception: Propagates initialization failures so partial startup does
                not continue with missing data producers or publishers.
        """
        assert self.peer_table is not None
        assert self.client is not None
        assert self.state_worker is not None

        try:
            self.sensor_manager = SensorManager(callback=self.sensor_event_queue.put)
            self.sensor_manager.load(self.config.sensors)
            self.sensor_manager.start_all()
            self.log.info(f"Started {len(self.sensor_manager.sensors)} sensors")

            self.publisher = SensorUpdatePublisher(
                self_node_id=self.config.node_id,
                peer_table=self.peer_table,
                tcp_client=self.client,
                state_worker=self.state_worker,
                log=self.log,
            )
            self.publisher.start()
            self.log.info("Sensor update publisher started")
        except Exception:
            self.log.critical("Failed to initialize sensors", exc_info=True)
            raise

    def _start_web_api(self) -> None:
        """Start the HTTP monitoring API backed by state snapshots.

        Returns:
            None: This method starts the HTTP monitoring API.

        Raises:
            Exception: Propagates API startup failures to keep process startup consistent.
        """
        assert self.state_worker is not None

        try:
            self.log.info(
                f"Starting WebAPI on {self.config.host}:{self.config.web_api_port}"
            )
            self.web_api = WebAPIServer(
                host=self.config.host,
                port=self.config.web_api_port,
                state_provider=self.state_worker.get_state_snapshot,
                updates_provider=self.state_worker.get_updates_snapshot,
                log=self.log,
            )
            self.web_api.start()
            self.log.info("WebAPI started")
        except Exception:
            self.log.critical("Failed to start WebAPI", exc_info=True)
            raise
