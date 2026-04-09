"""Validate GOSSIP_STATE handler behavior for membership liveness."""

from __future__ import annotations

import time

from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus
from protocol.factory import build_gossip_state
from protocol.handlers import make_gossip_state_handler


def _membership_state(
    *,
    node_id: str,
    host: str,
    port: int,
    status: str,
    status_ts_ms: int,
) -> dict[str, object]:
    return {
        "membership": {
            "peers": [
                {
                    "node_id": node_id,
                    "host": host,
                    "port": port,
                    "status": status,
                    "status_ts_ms": status_ts_ms,
                }
            ]
        }
    }


def test_gossip_state_handler_merges_membership_status() -> None:
    """Assert gossip state merges remote liveness status by timestamp."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None

    handler = make_gossip_state_handler(
        peer_table=peer_table,
        self_node_id="node-a",
    )
    handler(
        build_gossip_state(
            sender_id="node-x",
            state=_membership_state(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                status="dead",
                status_ts_ms=current.status_ts_ms + 10,
            ),
        )
    )

    peer = peer_table.get_peer("node-b")
    assert peer is not None
    assert peer.status is NodeStatus.DEAD
    assert peer.status_ts_ms == current.status_ts_ms + 10


def test_gossip_state_handler_ignores_stale_remote_status() -> None:
    """Assert stale remote suspicion does not override fresher local alive."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    peer_table.record_heartbeat(
        "node-b",
        heartbeat_at=time.time() + 1000.0,
        arrived_at_monotonic_s=20.0,
    )
    alive = peer_table.get_peer("node-b")
    assert alive is not None

    handler = make_gossip_state_handler(
        peer_table=peer_table,
        self_node_id="node-a",
    )
    handler(
        build_gossip_state(
            sender_id="node-x",
            state=_membership_state(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                status="suspected",
                status_ts_ms=alive.status_ts_ms - 1,
            ),
        )
    )

    current = peer_table.get_peer("node-b")
    assert current is not None
    assert current.status is NodeStatus.ALIVE
    assert current.status_ts_ms == alive.status_ts_ms


def test_gossip_state_converges_under_delay_after_partition() -> None:
    """Assert delayed stale gossip is ignored and newer gossip converges peers."""
    table_a = PeerTable(self_node_id="node-a")
    table_b = PeerTable(self_node_id="node-b")
    table_a.upsert_peer(node_id="node-c", host="10.0.0.3", port=9003)
    table_b.upsert_peer(node_id="node-c", host="10.0.0.3", port=9003)
    table_a_current = table_a.get_peer("node-c")
    table_b_current = table_b.get_peer("node-c")
    assert table_a_current is not None
    assert table_b_current is not None

    # Partition window: A learns a newer dead status, B remains on old alive.
    table_a.merge_gossip_state(
        [
            Peer(
                node_id="node-c",
                host="10.0.0.3",
                port=9003,
                liveness=NodeLiveness(
                    last_heartbeat=1.0,
                    phi=0.0,
                    status=NodeStatus.DEAD,
                    status_ts_ms=table_a_current.status_ts_ms + 20,
                ),
            ),
        ]
    )

    handler_a = make_gossip_state_handler(peer_table=table_a, self_node_id="node-a")
    handler_b = make_gossip_state_handler(peer_table=table_b, self_node_id="node-b")

    # Delayed stale gossip from B arrives at A and must not override.
    handler_a(
        build_gossip_state(
            sender_id="node-b",
            state=_membership_state(
                node_id="node-c",
                host="10.0.0.3",
                port=9003,
                status="alive",
                status_ts_ms=table_b_current.status_ts_ms,
            ),
        )
    )
    after_stale = table_a.get_peer("node-c")
    assert after_stale is not None
    assert after_stale.status is NodeStatus.DEAD

    # Newer gossip from A reaches B and B converges.
    handler_b(
        build_gossip_state(
            sender_id="node-a",
            state=table_a.build_gossip_state(),
        )
    )
    converged = table_b.get_peer("node-c")
    assert converged is not None
    assert converged.status is NodeStatus.DEAD
    assert converged.status_ts_ms == table_a_current.status_ts_ms + 20
