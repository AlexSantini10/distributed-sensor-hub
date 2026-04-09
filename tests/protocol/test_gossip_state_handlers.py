"""Validate GOSSIP_STATE handler behavior for membership liveness."""

from __future__ import annotations

import logging
import time

from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus
from protocol.factory import build_gossip_state
from protocol.handlers import make_gossip_state_handler
from utils.typing import JsonObject


def _membership_state(
    *,
    node_id: str,
    host: str,
    port: int,
    status: str,
    status_ts_ms: int,
) -> JsonObject:
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


def test_gossip_state_handler_merges_only_valid_entries_in_mixed_payload() -> None:
    """Assert mixed gossip payloads merge valid peers and skip malformed entries."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None

    discovered: list[str] = []
    handler = make_gossip_state_handler(
        peer_table=peer_table,
        self_node_id="node-a",
        on_peer_discovered=lambda peer: discovered.append(peer.node_id),
    )
    handler(
        build_gossip_state(
            sender_id="node-x",
            state={
                "membership": {
                    "peers": [
                        {
                            "node_id": "node-b",
                            "host": "10.0.0.22",
                            "port": 9022,
                            "status": "dead",
                            "status_ts_ms": current.status_ts_ms + 10,
                        },
                        {
                            "node_id": "node-c",
                            "host": "10.0.0.3",
                            "port": 9003,
                            "status": "alive",
                            "status_ts_ms": 5000,
                        },
                        {
                            "node_id": "node-a",
                            "host": "10.0.0.1",
                            "port": 9001,
                            "status": "alive",
                            "status_ts_ms": 5001,
                        },
                        {
                            "node_id": "node-d",
                            "host": "",
                            "port": 9004,
                            "status": "alive",
                            "status_ts_ms": 5002,
                        },
                        {
                            "node_id": "node-e",
                            "host": "10.0.0.5",
                            "port": "9005",
                            "status": "alive",
                            "status_ts_ms": 5003,
                        },
                        {
                            "node_id": "node-f",
                            "host": "10.0.0.6",
                            "port": 9006,
                            "status": "zombie",
                            "status_ts_ms": 5004,
                        },
                        "not-an-object",
                    ]
                }
            },
        )
    )

    updated_b = peer_table.get_peer("node-b")
    assert updated_b is not None
    assert updated_b.host == "10.0.0.22"
    assert updated_b.port == 9022
    assert updated_b.status is NodeStatus.DEAD
    assert updated_b.status_ts_ms == current.status_ts_ms + 10

    assert peer_table.get_peer("node-c") is not None
    assert discovered == ["node-c"]
    assert peer_table.get_peer("node-a") is None
    assert peer_table.get_peer("node-d") is None
    assert peer_table.get_peer("node-e") is None
    assert peer_table.get_peer("node-f") is None


def test_gossip_state_handler_survives_discovery_callback_failure(caplog) -> None:
    """Assert discovery callback failures are logged and do not abort merge."""
    peer_table = PeerTable(self_node_id="node-a")

    def failing_callback(peer: Peer) -> None:
        raise RuntimeError(f"cannot handle {peer.node_id}")

    handler = make_gossip_state_handler(
        peer_table=peer_table,
        self_node_id="node-a",
        on_peer_discovered=failing_callback,
    )

    with caplog.at_level(logging.WARNING, logger="gossip.handlers"):
        handler(
            build_gossip_state(
                sender_id="node-x",
                state=_membership_state(
                    node_id="node-c",
                    host="10.0.0.3",
                    port=9003,
                    status="alive",
                    status_ts_ms=5000,
                ),
            )
        )

    assert peer_table.get_peer("node-c") is not None
    assert "on_peer_discovered failed for peer node-c 10.0.0.3:9003" in caplog.text
