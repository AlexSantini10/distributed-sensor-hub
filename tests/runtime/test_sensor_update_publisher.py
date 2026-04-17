"""Validate push-pull fanout behavior of the sensor update publisher."""

from __future__ import annotations

from dataclasses import dataclass

from protocol.message import Message
from protocol.message_types import MessageType
from runtime.sensor_update_publisher import SensorUpdatePublisher


@dataclass(frozen=True)
class DummyPeer:
    """Provide the minimum peer surface used by the publisher."""

    node_id: str
    host: str
    port: int
    status: str


class DummyPeerTable:
    """Expose a fixed peer snapshot for publisher tests."""

    def __init__(self, peers: tuple[DummyPeer, ...]) -> None:
        self._peers = peers

    def snapshot(self) -> tuple[DummyPeer, ...]:
        return self._peers


class DummyClient:
    """Capture outbound messages sent by the publisher."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Message]] = []

    def send_json(self, peer_id: str, obj: Message) -> None:
        self.sent.append((peer_id, obj))

    def add_peer(self, peer) -> None:  # pragma: no cover - not used in these tests
        _ = peer


class DummyStateWorker:
    """Provide deterministic deltas and origin watermarks for tests."""

    def __init__(self, *, batches, origin_latest: dict[str, int] | None = None) -> None:
        self._batches = list(batches)
        self._origin_latest = {} if origin_latest is None else dict(origin_latest)

    def pop_replication_deltas(self):
        if not self._batches:
            return ()
        return self._batches.pop(0)

    def get_latest_timestamp_for_origin(self, origin: str) -> int:
        return self._origin_latest.get(origin, 0)


class DummyLog:
    """Provide the minimal logger surface consumed by the publisher."""

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


class DummyPullResponseTracker:
    """Capture peers marked as pending pull responses."""

    def __init__(self) -> None:
        self.marked: list[str] = []

    def mark_pull_requested(self, peer_id: str, *, window_s: float | None = None) -> None:
        _ = window_s
        self.marked.append(peer_id)


def test_publisher_uses_ratio_plus_minimum_fanout_for_push_and_pull() -> None:
    """Assert push and pull fanout are scaled from alive peers using ratio+minimum."""
    peers = tuple(
        DummyPeer(node_id=f"node-{idx}", host="10.0.0.1", port=9000 + idx, status="alive")
        for idx in range(1, 11)
    )
    state_worker = DummyStateWorker(
        batches=(
            (
                {
                    "sensor_id": "s1",
                    "value": 10,
                    "ts_ms": 1000,
                    "origin": "node-self",
                    "meta": {"unit": "C", "period_ms": 1000},
                },
            ),
            (),
        ),
        origin_latest={"node-1": 900},
    )
    client = DummyClient()

    publisher = SensorUpdatePublisher(
        self_node_id="node-self",
        peer_table=DummyPeerTable(peers),
        tcp_client=client,
        state_worker=state_worker,
        log=DummyLog(),
        push_ratio=0.2,
        push_min_peers=2,
        pull_ratio=0.1,
        pull_min_peers=1,
        pull_every_rounds=2,
        random_seed=7,
    )

    publisher._round = 1
    publisher._run_round()
    publisher._round = 2
    publisher._run_round()

    push_msgs = [item for item in client.sent if item[1].msg_type is MessageType.SENSOR_UPDATE]
    pull_msgs = [item for item in client.sent if item[1].msg_type is MessageType.GET_DELTA]

    assert len(push_msgs) == 2
    assert len(pull_msgs) == 1


def test_publisher_targets_alive_peers_only() -> None:
    """Assert push-pull selection excludes non-alive peers."""
    peers = (
        DummyPeer(node_id="node-a", host="10.0.0.1", port=9001, status="alive"),
        DummyPeer(node_id="node-b", host="10.0.0.2", port=9002, status="dead"),
        DummyPeer(node_id="node-c", host="10.0.0.3", port=9003, status="alive"),
    )
    state_worker = DummyStateWorker(
        batches=(
            (
                {
                    "sensor_id": "s1",
                    "value": 1,
                    "ts_ms": 1000,
                    "origin": "node-self",
                    "meta": {},
                },
            ),
        ),
        origin_latest={"node-a": 999, "node-b": 999, "node-c": 999},
    )
    client = DummyClient()

    publisher = SensorUpdatePublisher(
        self_node_id="node-self",
        peer_table=DummyPeerTable(peers),
        tcp_client=client,
        state_worker=state_worker,
        log=DummyLog(),
        push_ratio=1.0,
        push_min_peers=1,
        pull_ratio=1.0,
        pull_min_peers=1,
        pull_every_rounds=1,
        random_seed=3,
    )

    publisher._round = 1
    publisher._run_round()

    targeted_peer_ids = {peer_id for peer_id, _ in client.sent}
    assert "node-b" not in targeted_peer_ids
    assert targeted_peer_ids == {"node-a", "node-c"}


def test_publisher_marks_pull_requests_for_classification() -> None:
    """Assert successful GET_DELTA sends mark pull-pending windows."""
    peers = (
        DummyPeer(node_id="node-a", host="10.0.0.1", port=9001, status="alive"),
    )
    state_worker = DummyStateWorker(
        batches=((),),
        origin_latest={"node-a": 900},
    )
    client = DummyClient()
    tracker = DummyPullResponseTracker()

    publisher = SensorUpdatePublisher(
        self_node_id="node-self",
        peer_table=DummyPeerTable(peers),
        tcp_client=client,
        state_worker=state_worker,
        log=DummyLog(),
        push_ratio=0.0,
        push_min_peers=0,
        pull_ratio=1.0,
        pull_min_peers=1,
        pull_every_rounds=1,
        pull_response_tracker=tracker,
        random_seed=1,
    )

    publisher._round = 1
    publisher._run_round()

    assert tracker.marked == ["node-a"]
