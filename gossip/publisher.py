"""Publish membership gossip snapshots to known peers.

Responsibilities:
    - Build one ``GOSSIP_STATE`` message snapshot per publication round.
    - Broadcast the snapshot best-effort to all known peers.
    - Keep gossip transport concerns out of heartbeat/failure-detector logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import build_gossip_state
from topology.state import TopologyStateStore
from utils.logging import demo_event
from utils.typing import JsonObject, LoggerLike, SenderLike


def publish_membership_gossip(
    *,
    self_node_id: str,
    peer_table: PeerTable,
    peers: Iterable[Peer],
    send: SenderLike,
    log: LoggerLike,
    topology_state: TopologyStateStore | None = None,
    on_protocol_event: (
        Callable[[str, str | None, str | None, JsonObject | None], None] | None
    ) = None,
    on_metric: Callable[[str, int], None] | None = None,
) -> None:
    """Broadcast one membership gossip snapshot to the provided peers."""
    state = peer_table.build_gossip_state()
    if topology_state is not None:
        topology_fragment = topology_state.build_gossip_state()
        topology_obj = topology_fragment.get("topology")
        if isinstance(topology_obj, dict):
            state["topology"] = topology_obj

    gossip = build_gossip_state(
        sender_id=self_node_id,
        state=state,
    )
    membership = state.get("membership")
    updates_count = 0
    if isinstance(membership, dict):
        peers_list = membership.get("peers")
        if isinstance(peers_list, list):
            updates_count = len(peers_list)
    for peer in peers:
        try:
            send(peer.node_id, gossip)
            demo_event(
                log,
                "GOSSIP_PUSH",
                **{"from": self_node_id, "to": peer.node_id, "updates": updates_count},
            )
            if on_metric is not None:
                on_metric("gossip_messages_sent_total", 1)
            if on_protocol_event is not None:
                on_protocol_event(
                    "gossip_state_sent",
                    self_node_id,
                    peer.node_id,
                    None,
                )
        except Exception:
            log.debug(
                f"GOSSIP_STATE send failed to {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )

