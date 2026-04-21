"""Publish membership gossip snapshots to known peers.

Responsibilities:
    - Build one ``GOSSIP_STATE`` message snapshot per publication round.
    - Broadcast the snapshot best-effort to all known peers.
    - Keep gossip transport concerns out of heartbeat/failure-detector logic.
"""

from __future__ import annotations

from collections.abc import Iterable

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import build_gossip_state
from topology.state import TopologyStateStore
from utils.typing import LoggerLike, SenderLike


def publish_membership_gossip(
    *,
    self_node_id: str,
    peer_table: PeerTable,
    peers: Iterable[Peer],
    send: SenderLike,
    log: LoggerLike,
    topology_state: TopologyStateStore | None = None,
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
    for peer in peers:
        try:
            send(peer.node_id, gossip)
        except Exception:
            log.debug(
                f"GOSSIP_STATE send failed to {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )

