"""Validate LWW state resolution and snapshot shaping.

Responsibilities:
    - Assert insert, stale-update, and tie-break behavior for logical sensors.
    - Verify that snapshots expose winners under ``origin:sensor_id`` keys.
"""

from queue import Queue
import threading
import time
from typing import cast

from state.contracts import StateStoreLike
from state.node_state_store import NodeStateStore
from state.policy import MergeDecision
from state.node_state_store import SensorRecord
from state.node_state_worker import NodeStateWorker
from utils.typing import JsonObject, NodeSnapshot, SensorEventSource


class DummyLog:
    """Provide the minimal logger interface required by state-worker tests.

    Attributes:
        None
    """

    def debug(self, *args: object, **kwargs: object) -> None:
        pass

    def info(self, *args: object, **kwargs: object) -> None:
        """Accept informational logs without recording them.

        Args:
            *args (object): Positional log arguments.
            **kwargs (object): Keyword log arguments.

        Returns:
            None: This stub intentionally ignores all inputs.
        """
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        """Accept error logs without recording them.

        Args:
            *args (object): Positional log arguments.
            **kwargs (object): Keyword log arguments.

        Returns:
            None: This stub intentionally ignores all inputs.
        """
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def critical(self, *args: object, **kwargs: object) -> None:
        pass


def _event_queue() -> SensorEventSource:
    return cast(SensorEventSource, Queue())


def make_worker(node_id: str = "A") -> NodeStateWorker:
    """Create a state worker backed by a fresh in-memory queue.

    Args:
        node_id (str): Local node identifier assigned to the worker.

    Returns:
        NodeStateWorker: Worker configured with a dummy logger and empty queue.
    """
    q = _event_queue()
    return NodeStateWorker(node_id=node_id, event_queue=q, log=DummyLog())


class ReverseTieBreakPolicy:
    """Prefer lexicographically lower origins when timestamps are equal."""

    def decide(
        self,
        *,
        current: SensorRecord,
        candidate: SensorRecord,
    ) -> MergeDecision:
        if candidate.ts_ms > current.ts_ms:
            return "newer_ts"
        if candidate.ts_ms == current.ts_ms and candidate.origin < current.origin:
            return "tie_break"
        return "stale"


def test_new_insert() -> None:
    """Assert that the first update for a sensor becomes the winner.

    Returns:
        None: This test asserts LWW insert semantics.
    """
    w = make_worker()

    applied = w.merge_update("s1", 10, 1000, "A")
    assert applied is True

    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 10
    assert state["A:s1"]["ts_ms"] == 1000
    assert state["A:s1"]["origin"] == "A"


def test_newer_timestamp_wins() -> None:
    """Assert that a higher timestamp replaces the previous winner.

    Returns:
        None: This test asserts primary LWW ordering by timestamp.
    """
    w = make_worker()

    w.merge_update("s1", 10, 1000, "A")
    applied = w.merge_update("s1", 20, 2000, "A")

    assert applied is True
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 20


def test_stale_timestamp_ignored() -> None:
    """Assert that an older timestamp cannot replace the current winner.

    Returns:
        None: This test asserts stale-update rejection.
    """
    w = make_worker()

    w.merge_update("s1", 10, 2000, "A")
    applied = w.merge_update("s1", 5, 1000, "A")

    assert applied is False
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 10


def test_tie_break_origin() -> None:
    """Assert that lexicographically larger origins win timestamp ties.

    Returns:
        None: This test asserts deterministic secondary LWW ordering.
    """
    w = make_worker()

    w.merge_update("s1", 10, 1000, "A")
    applied = w.merge_update("s1", 20, 1000, "B")

    assert applied is True
    state = w.get_state_snapshot()["A"]
    assert state["B:s1"]["value"] == 20
    assert state["B:s1"]["origin"] == "B"


def test_tie_break_origin_lower_loses() -> None:
    """Assert that lower origins lose when timestamps are equal.

    Returns:
        None: This test asserts deterministic loss for lower tie-break values.
    """
    w = make_worker()

    w.merge_update("s1", 10, 1000, "B")
    applied = w.merge_update("s1", 20, 1000, "A")

    assert applied is False
    state = w.get_state_snapshot()["A"]
    assert state["B:s1"]["value"] == 10
    assert state["B:s1"]["origin"] == "B"


def test_merge_policy_is_injected_via_dependency_inversion() -> None:
    """Assert state conflict policy can be replaced through dependency injection."""
    w = NodeStateWorker(
        node_id="A",
        event_queue=_event_queue(),
        log=DummyLog(),
        merge_policy=ReverseTieBreakPolicy(),
    )

    w.merge_update("s1", 10, 1000, "B")
    applied = w.merge_update("s1", 20, 1000, "A")

    assert applied is True
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 20
    assert state["A:s1"]["origin"] == "A"


def test_store_is_injected_via_state_store_contract() -> None:
    """Assert the worker can collaborate with any store implementing the contract."""
    store = cast(StateStoreLike, NodeStateStore())
    w = NodeStateWorker(
        node_id="A",
        event_queue=_event_queue(),
        log=DummyLog(),
        store=store,
    )

    applied = w.merge_update("s1", 10, 1000, "A")

    assert applied is True
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 10


def test_apply_update_uses_local_origin() -> None:
    """Assert ``apply_update`` stores values with local worker origin."""
    w = make_worker(node_id="A")

    applied = w.apply_update(sensor_id="s2", value=99, timestamp=1234)
    assert applied is True

    state = w.get_state_snapshot()["A"]
    assert state["A:s2"]["value"] == 99
    assert state["A:s2"]["ts_ms"] == 1234
    assert state["A:s2"]["origin"] == "A"


def test_merge_update_rejects_empty_sensor_or_origin() -> None:
    """Assert merge_update rejects invalid identifiers and keeps state unchanged."""
    w = make_worker(node_id="A")

    assert w.merge_update("", 1, 1000, "A") is False
    assert w.merge_update("s1", 1, 1000, "") is False
    assert w.get_state_snapshot()["A"] == {}


def test_merge_state_ignores_non_mapping_payload() -> None:
    """Assert merge_state safely ignores non-dict payloads."""
    w = make_worker(node_id="A")
    w.merge_update("s1", 10, 1000, "A")

    merged = w.merge_state(remote_full_state="not-a-dict")  # type: ignore[arg-type]

    assert merged == 0
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 10


def test_merge_state_full_sync_flat_shape() -> None:
    """Assert bulk merge supports flat ``{sensor_id: {value, timestamp}}`` shape."""
    w = make_worker(node_id="A")
    w.merge_update("s1", 10, 1000, "A")

    merged = w.merge_state(
        {
            "s1": {"value": 50, "timestamp": 900, "origin": "B"},
            "s2": {"value": 20, "timestamp": 2000, "origin": "B"},
        }
    )

    assert merged == 1
    state = w.get_state_snapshot()["A"]
    assert state["A:s1"]["value"] == 10
    assert state["B:s2"]["value"] == 20


def test_merge_state_full_sync_snapshot_shape() -> None:
    """Assert bulk merge supports grouped node snapshot shape."""
    w = make_worker(node_id="A")

    merged = w.merge_state(
        {
            "B": {
                "B:s3": {
                    "value": 31,
                    "ts_ms": 3000,
                    "origin": "B",
                    "meta": {"unit": "C", "period_ms": 1000},
                }
            }
        }
    )

    assert merged == 1
    state = w.get_state_snapshot()["A"]
    assert state["B:s3"]["value"] == 31
    assert state["B:s3"]["ts_ms"] == 3000
    assert state["B:s3"]["origin"] == "B"


def test_merge_state_rejects_partial_payload_when_requested() -> None:
    """Assert strict full-sync merge rejects mixed valid/invalid payloads atomically."""
    w = make_worker(node_id="A")

    merged = w.merge_state(
        {
            "B": {
                "B:s1": {
                    "value": 11,
                    "ts_ms": 2000,
                    "origin": "B",
                    "meta": {"unit": "C", "period_ms": 1000},
                },
                "B:s2": {
                    "value": 12,
                    "origin": "B",
                },
            }
        },
        reject_partial=True,
    )

    assert merged == 0
    state = w.get_state_snapshot()["A"]
    assert state == {}


def test_merge_state_converges_after_partition() -> None:
    """Assert full-state exchange converges two diverged nodes to the same winners."""
    a = make_worker(node_id="A")
    b = make_worker(node_id="B")

    a.merge_update("s1", 10, 1000, "A")
    b.merge_update("s1", 20, 900, "B")
    b.merge_update("s2", 30, 1100, "B")

    b.merge_state(a.get_state_snapshot())
    a.merge_state(b.get_state_snapshot())

    a_state = a.get_state_snapshot()["A"]
    b_state = b.get_state_snapshot()["B"]
    assert a_state["A:s1"]["value"] == b_state["A:s1"]["value"] == 10
    assert a_state["B:s2"]["value"] == b_state["B:s2"]["value"] == 30


def test_merge_state_is_atomic_against_concurrent_updates() -> None:
    """Assert full-state merge keeps the store lock for the entire batch merge."""
    w = make_worker(node_id="A")
    store = cast(NodeStateStore, w._store)
    original_apply = store._apply_winner

    start_concurrent_update = threading.Event()
    update_finished = threading.Event()
    update_interleaved_inside_merge = {"value": False}

    def wrapped_apply(sensor_id: str, record: SensorRecord, *, ui_source: str) -> None:
        if sensor_id == "s1":
            start_concurrent_update.set()
            # Keep lock held long enough to let the competing thread contend.
            time.sleep(0.05)
        if sensor_id == "s2" and update_finished.is_set():
            update_interleaved_inside_merge["value"] = True
        original_apply(sensor_id, record, ui_source=ui_source)

    store._apply_winner = wrapped_apply

    def concurrent_update() -> None:
        start_concurrent_update.wait(timeout=1.0)
        w.merge_update("s-thread", 1, 500, "T")
        update_finished.set()

    payload: JsonObject | NodeSnapshot = {
        "B": {
            "B:s1": {"value": 1, "ts_ms": 200, "origin": "B", "meta": {}},
            "B:s2": {"value": 2, "ts_ms": 201, "origin": "B", "meta": {}},
        }
    }

    thread = threading.Thread(target=concurrent_update, daemon=True)
    thread.start()
    try:
        merged = w.merge_state(payload)
    finally:
        store._apply_winner = original_apply

    thread.join(timeout=1.0)

    assert merged == 2
    assert update_interleaved_inside_merge["value"] is False


def test_replication_delta_buffer_keeps_last_n_in_order() -> None:
    """Assert replication deltas retain append order and bounded last-N behavior."""
    w = NodeStateWorker(
        node_id="A",
        event_queue=_event_queue(),
        log=DummyLog(),
        replication_delta_maxlen=3,
    )

    w.merge_update("s1", 1, 1000, "A")
    w.merge_update("s2", 2, 1001, "A")
    w.merge_update("s3", 3, 1002, "A")
    w.merge_update("s4", 4, 1003, "A")

    deltas = w.pop_replication_deltas()
    assert [d["sensor_id"] for d in deltas] == ["s2", "s3", "s4"]
    assert [d["ts_ms"] for d in deltas] == [1001, 1002, 1003]


def test_replication_delta_drain_is_incremental() -> None:
    """Assert delta drains only return unread events after each pop."""
    w = make_worker(node_id="A")
    w.merge_update("s1", 1, 1000, "A")
    first = w.pop_replication_deltas()
    second = w.pop_replication_deltas()

    assert len(first) == 1
    assert first[0]["sensor_id"] == "s1"
    assert second == ()

    w.merge_update("s2", 2, 1001, "A")
    third = w.pop_replication_deltas()
    assert len(third) == 1
    assert third[0]["sensor_id"] == "s2"


def test_replication_delta_since_returns_none_when_cursor_is_too_old() -> None:
    """Assert stale delta cursors are rejected when history has rotated."""
    w = NodeStateWorker(
        node_id="A",
        event_queue=_event_queue(),
        log=DummyLog(),
        replication_delta_maxlen=2,
    )
    w.merge_update("s1", 1, 1000, "A")
    w.merge_update("s2", 2, 1001, "A")
    w.merge_update("s3", 3, 1002, "A")

    assert w.get_replication_deltas_since(since_ts_ms=999) is None
    valid = w.get_replication_deltas_since(since_ts_ms=1001)
    assert valid is not None
    assert [d["sensor_id"] for d in valid] == ["s3"]


def test_get_latest_timestamp_for_origin_reads_current_winners() -> None:
    """Assert origin watermark reflects current winning records only."""
    w = make_worker(node_id="A")
    w.merge_update("s1", 1, 1000, "node-b")
    w.merge_update("s2", 2, 1500, "node-b")
    w.merge_update("s2", 3, 2000, "node-c")

    assert w.get_latest_timestamp_for_origin("node-b") == 1000
    assert w.get_latest_timestamp_for_origin("node-c") == 2000
    assert w.get_latest_timestamp_for_origin("node-z") == 0


def test_updates_snapshot_includes_sync_source_for_ui_logs() -> None:
    """Assert UI updates expose sync_source metadata for log attribution."""
    w = make_worker(node_id="A")
    w.merge_update("s1", 10, 1000, "node-b", source="pull")

    updates = w.get_updates_snapshot()["A"]
    assert updates["node-b:s1"]["sync_source"] == "pull"
