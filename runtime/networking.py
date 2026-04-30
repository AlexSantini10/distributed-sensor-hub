"""Assemble runtime networking and membership bootstrap behavior.

Responsibilities:
    - Build the transport and protocol stack used by a runtime node.
    - Convert configured bootstrap addresses into initial membership seeds.
    - Register discovered peers so gossip and state dissemination can converge.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from membership.peer import Peer as MembershipPeer
from membership.peer_table import PeerTable
from networking.tcp_client import Peer as TcpPeer
from networking.tcp_client import TcpClient
from networking.tcp_server import TcpServer
from protocol.contracts import NetworkConstant
from protocol.dispatcher import MessageDispatcher
from protocol.factory import build_join_request
from protocol.message import Message
from topology.models import TopologyContext, TopologyPeer
from topology.policy import TopologyPolicy
from topology.resolver import resolve_topology_policy
from topology.state import TopologyStateStore
from utils.config import Config
from utils.logging import demo_event
from utils.typing import JsonObject, LoggerLike, SenderLike, StateWorkerLike
from runtime.protocol_assembly import setup_protocol
from runtime.pull_response_tracker import PullResponseTracker


@dataclass(frozen=True)
class NetworkingContext:
    """Bundle the networking objects required by the runtime.

    Attributes:
        client (TcpClient): Outbound TCP client used to send protocol messages to peers.
        server (TcpServer): Inbound server that accepts and dispatches protocol messages.
        dispatcher (MessageDispatcher): Protocol dispatcher that routes decoded messages to handlers.
        peer_table (PeerTable): Membership view updated by protocol handlers and gossip.
        bootstrap_peers (list[TcpPeer]): Configured peers available for initial cluster contact.
        topology_policy (TopologyPolicy): Topology policy driving connect-target decisions.
        pull_response_tracker (PullResponseTracker): Pull-window tracker used to
            classify inbound state updates as push or pull.
        topology_state (TopologyStateStore): Disseminated topology state store
            containing local declaration and merged global topology view.
    """

    client: TcpClient
    server: TcpServer
    dispatcher: MessageDispatcher
    peer_table: PeerTable
    bootstrap_peers: list[TcpPeer]
    topology_policy: TopologyPolicy
    pull_response_tracker: PullResponseTracker
    topology_state: TopologyStateStore


def make_join_request(self_node_id: str, host: str, port: int) -> Message:
    """Build a membership ``JOIN_REQUEST`` message.

    Args:
        self_node_id (str): Stable identifier of the local node.
        host (str): Advertised host that peers should use for future connections.
        port (int): Advertised TCP port that peers should use for future connections.

    Returns:
        Message: Protocol message announcing the local node's reachable endpoint.
    """
    return build_join_request(
        sender_id=self_node_id,
        node_id=self_node_id,
        host=host,
        port=port,
    )


def bootstrap_membership(
    self_node_id: str,
    host: str,
    port: int,
    peers: list[TcpPeer],
    send: SenderLike,
    log: LoggerLike,
) -> None:
    """Send ``JOIN_REQUEST`` messages to configured bootstrap peers.

    Args:
        self_node_id (str): Stable identifier of the local node.
        host (str): Advertised host for the local node.
        port (int): Advertised TCP port for the local node.
        peers (list[TcpPeer]): Bootstrap peers that should receive the initial join attempt.
        send (SenderLike): Function that transmits a protocol message to a peer by node ID.
        log (LoggerLike): Logger used for membership bootstrap diagnostics.

    Returns:
        None: This function emits best-effort join messages to bootstrap peers.
    """
    join_msg = make_join_request(
        self_node_id=self_node_id,
        host=host,
        port=port,
    )

    for peer in peers:
        try:
            send(peer.node_id, join_msg)
            log.info(f"Sent JOIN_REQUEST to {peer.host}:{peer.port}")
        except Exception:
            log.error(
                f"JOIN_REQUEST failed to {peer.host}:{peer.port}",
                exc_info=True,
            )


def resolve_peer_host(node_id: str, advertised_host: str) -> str:
    """Resolve a connectable host from an advertised endpoint.

    Args:
        node_id (str): Peer identifier, which may also be a routable service name.
        advertised_host (str): Host value advertised by the peer.

    Returns:
        str: Host value suitable for outbound connections.

    A peer may bind to ``0.0.0.0`` locally, but that address is not usable as a
    remote destination. When that occurs, the node ID is treated as the
    connectable address contract for peer-to-peer traffic.
    """
    if advertised_host == NetworkConstant.WILDCARD_HOST.value:
        return node_id
    return advertised_host


class ClientPeerRegistry:
    """Track outbound client peers and suppress duplicate registrations.

    Attributes:
        _client (TcpClient): TCP client that owns the outbound peer list.
        _known_peer_ids (set[str]): Set of peer identifiers already registered locally.
        _pending_peer_ids (set[str]): Set of peer identifiers currently being registered.
        _lock (threading.Lock): Mutex guarding concurrent peer discovery updates.
    """

    def __init__(
        self,
        client: TcpClient,
        on_peer_connected: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the registry.

        Args:
            client (TcpClient): TCP client that should learn about discovered peers.

        Returns:
            None: This initializer configures the peer registry.
        """
        self._client = client
        self._on_peer_connected = on_peer_connected
        self._known_peer_ids: set[str] = set()
        self._pending_peer_ids: set[str] = set()
        self._lock = threading.Lock()

    def ensure_peer(self, node_id: str, host: str, port: int) -> None:
        """Register a peer with the outbound client if it is not known yet.

        Args:
            node_id (str): Stable identifier of the peer.
            host (str): Advertised host for the peer.
            port (int): Advertised TCP port for the peer.

        Returns:
            None: This method ensures the outbound client can address the peer.
        """
        with self._lock:
            if node_id in self._known_peer_ids or node_id in self._pending_peer_ids:
                return
            self._pending_peer_ids.add(node_id)

        connect_host = resolve_peer_host(node_id=node_id, advertised_host=host)

        try:
            self._client.add_peer(
                TcpPeer(
                    node_id=node_id,
                    host=connect_host,
                    port=port,
                )
            )
        except RuntimeError as exc:
            with self._lock:
                self._pending_peer_ids.discard(node_id)
                if "already exists" in str(exc).lower():
                    self._known_peer_ids.add(node_id)
                    return
            raise
        except Exception:
            with self._lock:
                self._pending_peer_ids.discard(node_id)
            raise

        with self._lock:
            self._pending_peer_ids.discard(node_id)
            self._known_peer_ids.add(node_id)
        if self._on_peer_connected is not None:
            self._on_peer_connected(node_id)

    def connected_peer_ids(self) -> tuple[str, ...]:
        """Return a snapshot of registered outbound peer node IDs.

        Returns:
            tuple[str, ...]: Stable sorted peer IDs known by the registry.
        """
        with self._lock:
            known = set(self._known_peer_ids)
        known.update(self._client.registered_peer_ids())
        return tuple(sorted(known))


def _to_topology_peer(*, node_id: str, host: str, port: int) -> TopologyPeer:
    """Build a policy peer descriptor from runtime endpoint data.

    Args:
        node_id (str): Stable node identifier.
        host (str): Advertised host.
        port (int): Advertised TCP port.

    Returns:
        TopologyPeer: Policy peer descriptor.
    """
    return TopologyPeer(node_id=node_id, host=host, port=port)


def _build_topology_context(
    *,
    known_peers: tuple[TopologyPeer, ...],
    connected_peers: tuple[str, ...],
    bootstrap_peers: tuple[TopologyPeer, ...],
) -> TopologyContext:
    """Build a minimal topology context for policy decisions.

    Args:
        known_peers (tuple[TopologyPeer, ...]): Membership/discovery known peers.
        connected_peers (tuple[str, ...]): Registered outbound transport peers.
        bootstrap_peers (tuple[TopologyPeer, ...]): Configured bootstrap peers.

    Returns:
        TopologyContext: Immutable topology decision context.
    """
    return TopologyContext(
        known_peers=known_peers,
        connected_peers=connected_peers,
        bootstrap_peers=bootstrap_peers,
    )


def build_bootstrap_peers(
    bootstrap_peers: tuple[tuple[str, int], ...],
    registry: ClientPeerRegistry,
    topology_policy: TopologyPolicy,
) -> list[TcpPeer]:
    """Register configured bootstrap peers with the outbound client.

    Args:
        bootstrap_peers (tuple[tuple[str, int], ...]): Host and port pairs configured
            for initial cluster contact.
        registry (ClientPeerRegistry): Outbound peer registry used to register selected peers.
        topology_policy (TopologyPolicy): Policy used to select and resolve connect targets.

    Returns:
        list[TcpPeer]: Peer descriptors representing the configured bootstrap targets.
    """
    registered_peers: list[TcpPeer] = []
    bootstrap_policy_peers: list[TopologyPeer] = []

    for host, port in bootstrap_peers:
        peer_id = f"bootstrap@{host}:{port}"
        peer = TcpPeer(node_id=peer_id, host=host, port=port)
        bootstrap_policy_peers.append(
            _to_topology_peer(node_id=peer.node_id, host=peer.host, port=peer.port)
        )
        registered_peers.append(peer)

    selected = topology_policy.select_peers_to_connect(
        _build_topology_context(
            known_peers=(),
            connected_peers=registry.connected_peer_ids(),
            bootstrap_peers=tuple(bootstrap_policy_peers),
        )
    )
    for candidate in selected:
        target = topology_policy.resolve_connection_target(candidate)
        registry.ensure_peer(
            node_id=target.node_id,
            host=target.host,
            port=target.port,
        )

    _ = topology_policy.select_peers_to_disconnect(
        _build_topology_context(
            known_peers=(),
            connected_peers=registry.connected_peer_ids(),
            bootstrap_peers=tuple(bootstrap_policy_peers),
        )
    )
    _ = topology_policy.handle_under_connected(
        _build_topology_context(
            known_peers=(),
            connected_peers=registry.connected_peer_ids(),
            bootstrap_peers=tuple(bootstrap_policy_peers),
        )
    )

    return registered_peers


def seed_peer_table(
    peer_table: PeerTable,
    bootstrap_peers: list[TcpPeer],
    log: LoggerLike,
) -> None:
    """Insert bootstrap peers into membership as a best-effort seed.

    Args:
        peer_table (PeerTable): Membership table consumed by gossip and message routing.
        bootstrap_peers (list[TcpPeer]): Peers that should appear in the initial membership view.
        log (LoggerLike): Logger used for best-effort seeding diagnostics.

    Returns:
        None: This function inserts configured peers into the initial membership view.
    """
    for peer in bootstrap_peers:
        if peer.node_id.startswith("bootstrap@"):
            continue
        try:
            peer_table.upsert_peer(
                node_id=peer.node_id,
                host=peer.host,
                port=peer.port,
            )
        except Exception:
            log.warning("Failed to seed bootstrap peer into PeerTable", exc_info=True)


def setup_node_networking(
    config: Config,
    log: LoggerLike,
    state_worker: StateWorkerLike,
    tcp_server_cls: type[TcpServer],
    on_protocol_event: (
        Callable[[str, str | None, str | None, JsonObject | None], None] | None
    ) = None,
    on_metric: Callable[[str, int], None] | None = None,
) -> NetworkingContext:
    """Create the runtime networking stack for a node.

    Args:
        config (Config): Runtime configuration containing node identity, bind address,
            and configured bootstrap peers.
        log (LoggerLike): Logger used for networking diagnostics.
        state_worker (StateWorkerLike): State worker used by protocol handlers to
            apply updates and serve snapshots.
        tcp_server_cls (type[TcpServer]): Server class used to bind inbound transport.

    Returns:
        NetworkingContext: Fully assembled networking objects for the runtime,
            including pull-response classification state.
    """
    client = TcpClient(
        network_delay_s=config.network_delay_ms / 1000.0,
        network_delay_jitter_s=config.network_delay_jitter_ms / 1000.0,
        network_delay_spike_prob=config.network_delay_spike_prob,
        network_delay_spike_s=config.network_delay_spike_ms / 1000.0,
        network_packet_loss_prob=config.network_packet_loss_prob,
    )
    topology_state = TopologyStateStore(self_node_id=config.node_id)

    def _on_peer_connected(node_id: str) -> None:
        topology_state.mark_neighbor_connected(node_id)
        demo_event(log, "PEER_CONNECTED", node=config.node_id, peer=node_id)

    registry = ClientPeerRegistry(
        client=client,
        on_peer_connected=_on_peer_connected,
    )
    topology_policy = resolve_topology_policy(config.topology_policy.value)

    def on_peer_discovered(peer: MembershipPeer) -> None:
        """Register a discovered peer and actively initiate reciprocal join.

        Args:
            peer (MembershipPeer): Membership entry discovered through gossip or join handling.

        Returns:
            None: This callback registers the peer and initiates reciprocal discovery.
        """
        known = (_to_topology_peer(node_id=peer.node_id, host=peer.host, port=peer.port),)
        selected = topology_policy.select_peers_to_connect(
            _build_topology_context(
                known_peers=known,
                connected_peers=registry.connected_peer_ids(),
                bootstrap_peers=(),
            )
        )
        for candidate in selected:
            target = topology_policy.resolve_connection_target(candidate)
            registry.ensure_peer(
                node_id=target.node_id,
                host=target.host,
                port=target.port,
            )

        join_msg = make_join_request(
            self_node_id=config.node_id,
            host=config.host,
            port=config.port,
        )

        try:
            client.send_json(peer.node_id, join_msg)
            log.info(
                f"Discovery JOIN_REQUEST sent to {peer.node_id} "
                f"{peer.host}:{peer.port}"
            )
        except Exception:
            log.warning(
                f"Discovery JOIN_REQUEST failed to {peer.node_id} "
                f"{peer.host}:{peer.port}",
                exc_info=True,
            )

    bootstrap_peers = build_bootstrap_peers(
        bootstrap_peers=config.bootstrap_peers,
        registry=registry,
        topology_policy=topology_policy,
    )
    pull_response_tracker = PullResponseTracker()

    dispatcher, peer_table = setup_protocol(
        self_node_id=config.node_id,
        send_function=client.send_json,
        state_worker=state_worker,
        on_peer_discovered=on_peer_discovered,
        sensor_update_source_classifier=pull_response_tracker.classify_sender,
        sensor_update_seq_observer=pull_response_tracker.observe_replication_seq,
        phi_threshold_suspect=config.phi_threshold_suspect,
        phi_threshold_dead=config.phi_threshold_dead,
        phi_initial_interval_s=config.phi_initial_interval_s,
        topology_state=topology_state,
        on_protocol_event=on_protocol_event,
        on_metric=on_metric,
    )

    topology_state.set_local_neighbors(registry.connected_peer_ids())

    server = tcp_server_cls(
        host=config.host,
        port=config.port,
        dispatcher=dispatcher,
        recv_timeout_s=config.socket_timeout_s,
        accept_timeout_s=config.socket_timeout_s,
        backlog=config.accept_queue_size,
        max_connections=config.max_connections,
        max_workers=config.max_workers,
    )

    return NetworkingContext(
        client=client,
        server=server,
        dispatcher=dispatcher,
        peer_table=peer_table,
        bootstrap_peers=bootstrap_peers,
        topology_policy=topology_policy,
        pull_response_tracker=pull_response_tracker,
        topology_state=topology_state,
    )
