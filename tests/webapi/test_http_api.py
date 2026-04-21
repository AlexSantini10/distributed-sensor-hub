"""Validate HTTP API snapshot endpoints for state, updates, and membership."""

from __future__ import annotations

import json
from urllib.request import urlopen

from utils.typing import MembershipSnapshotDict, NodeSnapshot
from webapi.http_api import WebAPIServer


class DummyLog:
    """Provide the minimal logger interface used by the Web API server."""

    def debug(self, *args: object, **kwargs: object) -> None:
        pass

    def info(self, *args: object, **kwargs: object) -> None:
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        pass

    def critical(self, *args: object, **kwargs: object) -> None:
        pass


def _fetch_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=2.0) as response:  # nosec: B310 - test-only local URL
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def test_http_api_serves_membership_snapshot() -> None:
    """Assert that `/api/membership` returns the provided membership payload."""
    state_snapshot: NodeSnapshot = {
        "node-a": {
            "node-a:sensor": {
                "value": 1,
                "ts_ms": 1,
                "origin": "node-a",
                "meta": {"unit": None, "period_ms": None},
            }
        }
    }
    updates_snapshot: NodeSnapshot = {"node-a": {}}
    membership_snapshot: MembershipSnapshotDict = {
        "local_node_id": "node-a",
        "peers": [
            {
                "peer_id": "node-b",
                "host": "127.0.0.1",
                "port": 9001,
                "status": "alive",
                "phi": 0.0,
                "last_heartbeat_ts_ms": 1000,
                "sample_count": 3,
                "sample_window_size": 128,
                "status_transition_ts_ms": 1000,
            }
        ],
    }

    server = WebAPIServer(
        host="127.0.0.1",
        port=0,
        state_provider=lambda: state_snapshot,
        updates_provider=lambda: updates_snapshot,
        membership_provider=lambda: membership_snapshot,
        topology_provider=lambda: {"local_node_id": "node-a", "adjacency": {}, "entries": []},
        log=DummyLog(),
    )
    server.start()
    try:
        port = server._server.server_port
        base = f"http://127.0.0.1:{port}"
        assert _fetch_json(f"{base}/api/state") == state_snapshot
        assert _fetch_json(f"{base}/api/updates") == updates_snapshot
        assert _fetch_json(f"{base}/api/membership") == membership_snapshot
        assert _fetch_json(f"{base}/api/topology") == {
            "local_node_id": "node-a",
            "adjacency": {},
            "entries": [],
        }
    finally:
        server.stop()
