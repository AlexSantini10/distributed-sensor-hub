"""Validate LWW state resolution and snapshot shaping.

Responsibilities:
    - Assert insert, stale-update, and tie-break behavior for logical sensors.
    - Verify that snapshots expose winners under ``origin:sensor_id`` keys.
"""

from queue import Queue

from state.node_state_worker import NodeStateWorker


class DummyLog:
    """Provide the minimal logger interface required by state-worker tests.

    Attributes:
        None
    """

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


def make_worker(node_id: str = "A") -> NodeStateWorker:
    """Create a state worker backed by a fresh in-memory queue.

    Args:
        node_id (str): Local node identifier assigned to the worker.

    Returns:
        NodeStateWorker: Worker configured with a dummy logger and empty queue.
    """
    q = Queue()
    return NodeStateWorker(node_id=node_id, event_queue=q, log=DummyLog())


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
