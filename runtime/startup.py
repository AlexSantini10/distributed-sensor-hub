"""Startup helpers used by ``NodeApplication`` to assemble runtime subsystems."""

from networking.tcp_client import TcpClient
from networking.tcp_server import TcpServer
from protocol.factory import build_full_sync_request
from runtime.heartbeat import HeartbeatSender
from runtime.networking import (
    bootstrap_membership,
    seed_peer_table,
    setup_node_networking,
)
from runtime.sensor_update_publisher import SensorUpdatePublisher
from runtime.pull_response_tracker import PullResponseTracker
from sensors.handler import QueueingSensorHandler
from sensors.sensor_manager import SensorManager
from state.events import SensorEventQueue
from state.node_state_worker import NodeStateWorker
from topology.state import TopologyStateStore
from utils.config import Config
from utils.logging import demo_event
from utils.typing import JsonSnapshotProvider, LoggerLike
from webapi.http_api import WebAPIServer


def start_state_worker(
    *,
    config: Config,
    event_queue: SensorEventQueue,
    log: LoggerLike,
) -> NodeStateWorker:
    """Create and start the local state worker."""
    state_worker = NodeStateWorker(
        node_id=config.node_id,
        event_queue=event_queue,
        log=log,
        replication_delta_maxlen=config.replication_delta_maxlen,
    )
    state_worker.start()
    log.info("State worker started")
    return state_worker


def start_networking_stack(
    *,
    config: Config,
    log: LoggerLike,
    state_worker: NodeStateWorker,
    tcp_server_cls: type[TcpServer],
    on_protocol_event=None,
    on_metric=None,
):
    """Create the protocol stack and start inbound networking."""
    networking = setup_node_networking(
        config=config,
        log=log,
        state_worker=state_worker,
        tcp_server_cls=tcp_server_cls,
        on_protocol_event=on_protocol_event,
        on_metric=on_metric,
    )

    try:
        networking.server.start()
    except Exception:
        log.critical("Failed to start TCP server", exc_info=True)
        raise

    log.info(f"Node listening on {config.host}:{config.port}")
    return networking


def bootstrap_cluster_membership(
    *,
    config: Config,
    peer_table,
    bootstrap_peers,
    client: TcpClient,
    log: LoggerLike,
) -> None:
    """Seed membership and contact bootstrap peers."""
    seed_peer_table(
        peer_table=peer_table,
        bootstrap_peers=bootstrap_peers,
        log=log,
    )

    if not bootstrap_peers:
        log.info("No bootstrap peers configured")
        return

    bootstrap_membership(
        self_node_id=config.node_id,
        host=config.host,
        port=config.port,
        peers=bootstrap_peers,
        send=client.send_json,
        log=log,
    )

    request = build_full_sync_request(
        sender_id=config.node_id,
        requester_id=config.node_id,
    )
    for peer in bootstrap_peers:
        try:
            client.send_json(peer.node_id, request)
            demo_event(
                log,
                "FULL_SYNC_REQUEST",
                **{"from": config.node_id, "to": peer.node_id},
            )
            log.info(
                f"Sent FULL_SYNC_REQUEST to {peer.node_id} {peer.host}:{peer.port}"
            )
        except Exception:
            log.warning(
                f"FULL_SYNC_REQUEST failed to {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )


def start_sensor_runtime(
    *,
    config: Config,
    event_queue: SensorEventQueue,
    peer_table,
    client: TcpClient,
    state_worker: NodeStateWorker,
    log: LoggerLike,
    pull_response_tracker: PullResponseTracker | None = None,
    on_protocol_event=None,
    on_metric=None,
) -> tuple[SensorManager, SensorUpdatePublisher]:
    """Start sensors and the outbound replication publisher.

    Args:
        config (Config): Runtime configuration with sensor and gossip settings.
        event_queue (SensorEventQueue): Shared queue receiving local sensor events.
        peer_table: Membership table used to select alive replication targets.
        client (TcpClient): Outbound transport used by the publisher.
        state_worker (NodeStateWorker): State worker providing deltas/cursors.
        log (LoggerLike): Logger used for startup diagnostics.
        pull_response_tracker (PullResponseTracker | None): Optional tracker used
            to classify inbound updates as pull responses.

    Returns:
        tuple[SensorManager, SensorUpdatePublisher]: Started sensor manager and publisher.
    """
    sensor_handler = QueueingSensorHandler(event_queue.put)
    sensor_manager = SensorManager(handler=sensor_handler)
    sensor_manager.load(config.sensors)
    sensor_manager.start_all()
    log.info(f"Started {len(sensor_manager.sensors)} sensors")

    publisher = SensorUpdatePublisher(
        self_node_id=config.node_id,
        peer_table=peer_table,
        tcp_client=client,
        state_worker=state_worker,
        log=log,
        interval_s=config.gossip_sync_interval_ms / 1000.0,
        push_ratio=config.gossip_push_ratio,
        push_min_peers=config.gossip_push_min_peers,
        pull_ratio=config.gossip_pull_ratio,
        pull_min_peers=config.gossip_pull_min_peers,
        pull_every_rounds=config.gossip_pull_every_rounds,
        pull_response_tracker=pull_response_tracker,
        on_protocol_event=on_protocol_event,
        on_metric=on_metric,
    )
    publisher.start()
    log.info("Sensor update publisher started")
    return sensor_manager, publisher


def start_heartbeat_runtime(
    *,
    config: Config,
    peer_table,
    client: TcpClient,
    log: LoggerLike,
    topology_state: TopologyStateStore | None = None,
    on_protocol_event=None,
    on_metric=None,
) -> HeartbeatSender:
    """Start periodic heartbeats to all peers."""
    heartbeat_sender = HeartbeatSender(
        self_node_id=config.node_id,
        peer_table=peer_table,
        send=client.send_json,
        interval_ms=config.heartbeat_interval_ms,
        log=log,
        connected_peer_ids_provider=client.registered_peer_ids,
        topology_state=topology_state,
        on_protocol_event=on_protocol_event,
        on_metric=on_metric,
    )
    heartbeat_sender.start()
    log.info(
        f"Heartbeat sender started (interval_ms={config.heartbeat_interval_ms})"
    )
    return heartbeat_sender


def start_web_api_server(
    *,
    config: Config,
    state_worker: NodeStateWorker,
    peer_table,
    log: LoggerLike,
    topology_state: TopologyStateStore | None = None,
    introspection_provider: JsonSnapshotProvider | None = None,
) -> WebAPIServer:
    """Start the HTTP monitoring API backed by state snapshots."""
    log.info(f"Starting WebAPI on {config.host}:{config.web_api_port}")
    web_api = WebAPIServer(
        host=config.host,
        port=config.web_api_port,
        state_provider=state_worker.get_state_snapshot,
        updates_provider=state_worker.get_updates_snapshot,
        membership_provider=(
            peer_table.membership_snapshot if peer_table is not None else None
        ),
        topology_provider=(
            topology_state.topology_snapshot if topology_state is not None else None
        ),
        introspection_provider=introspection_provider,
        log=log,
    )
    web_api.start()
    log.info("WebAPI started")
    return web_api
