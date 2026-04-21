"""Handle inbound gossip messages for membership convergence.

Responsibilities:
    - Validate and parse ``GOSSIP_STATE`` membership payloads.
    - Merge parsed peer liveness records into the local membership table.
    - Notify runtime hooks when gossip reveals previously unknown peers.
"""

from __future__ import annotations

from collections.abc import Callable
import time

from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus
from protocol.message import Message
from protocol.messages import GossipStatePayload
from topology.state import TopologyEntry, TopologyStateStore
from utils.logging import get_logger
from utils.typing import LoggerLike


def make_gossip_state_handler(
    *,
    peer_table: PeerTable,
    self_node_id: str,
    on_peer_discovered: Callable[[Peer], None] | None = None,
    topology_state: TopologyStateStore | None = None,
) -> Callable[[Message], None]:
    """Create a handler that merges membership liveness gossip."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def _notify_discovered(peer: Peer) -> None:
        if on_peer_discovered is None:
            return
        try:
            on_peer_discovered(peer)
        except Exception:
            log.warning(
                f"on_peer_discovered failed for peer {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )

    def _parse_membership_gossip(payload: GossipStatePayload) -> list[Peer]:
        state = payload.state
        membership = state.get("membership")
        if membership is None:
            return []
        if not isinstance(membership, dict):
            raise ValueError("state.membership must be an object")

        raw_peers = membership.get("peers", [])
        if not isinstance(raw_peers, list):
            raise ValueError("state.membership.peers must be a list")

        parsed: list[Peer] = []
        for index, raw in enumerate(raw_peers):
            if not isinstance(raw, dict):
                log.debug(f"Ignored gossip peer at index={index}: not an object")
                continue

            node_id = raw.get("node_id")
            host = raw.get("host")
            port = raw.get("port")
            status_raw = raw.get("status")
            status_ts_ms = raw.get("status_ts_ms")

            if (
                not isinstance(node_id, str)
                or node_id == ""
                or not isinstance(host, str)
                or host == ""
                or not isinstance(port, int)
                or not isinstance(status_raw, str)
                or not isinstance(status_ts_ms, int)
            ):
                log.debug(f"Ignored malformed gossip peer at index={index}")
                continue

            try:
                status = NodeStatus.from_wire(status_raw)
            except ValueError:
                log.debug(
                    f"Ignored gossip peer with unknown status at index={index}: {status_raw}"
                )
                continue

            parsed.append(
                Peer(
                    node_id=node_id,
                    host=host,
                    port=port,
                    liveness=NodeLiveness(
                        last_heartbeat=time.time(),
                        phi=0.0,
                        status=status,
                        status_ts_ms=status_ts_ms,
                    ),
                )
            )
        return parsed

    def handle_gossip_state(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, GossipStatePayload):
            log.warning("Invalid GOSSIP_STATE payload")
            return

        try:
            incoming = _parse_membership_gossip(payload)
        except ValueError as exc:
            log.warning(f"Invalid GOSSIP_STATE structure: {exc}")
            return

        if incoming:
            merge_result = peer_table.merge_gossip_state(incoming)
            for discovered in merge_result.new_peers:
                _notify_discovered(discovered)

            if merge_result.changed:
                log.info(
                    "GOSSIP_STATE merged: "
                    f"sender={msg.sender_id} "
                    f"merged={merge_result.merged_entries} "
                    f"new={len(merge_result.new_peers)} "
                    f"updated={len(merge_result.updated_peers)} "
                    f"ignored={merge_result.ignored_entries}"
                )

        if topology_state is None:
            return

        topology_raw = payload.state.get("topology")
        if topology_raw is None:
            return
        if not isinstance(topology_raw, dict):
            log.debug("Ignored malformed topology gossip: topology must be object")
            return

        raw_entries = topology_raw.get("entries", [])
        if not isinstance(raw_entries, list):
            log.debug("Ignored malformed topology gossip: entries must be list")
            return

        parsed_entries: list[TopologyEntry] = []
        for raw_entry in raw_entries:
            try:
                parsed_entries.append(TopologyEntry.from_mapping(raw_entry))
            except ValueError:
                log.debug("Ignored malformed topology entry in gossip payload")

        if not parsed_entries:
            return

        merged_topology = topology_state.merge_entries(parsed_entries)
        if merged_topology > 0:
            log.info(
                "GOSSIP_STATE topology merged: "
                f"sender={msg.sender_id} merged_entries={merged_topology}"
            )

    return handle_gossip_state


def handle_gossip_state(msg: Message) -> None:
    """Warn that state-gossip handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("GOSSIP_STATE received but handler is not wired")

