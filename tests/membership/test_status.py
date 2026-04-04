"""Validate typed membership-status behavior."""

from membership.status import NodeStatus


def test_node_status_wire_round_trip() -> None:
    """Assert that node-status serialization stays string-compatible.

    Returns:
        None: This test asserts the explicit wire mapping.
    """
    assert NodeStatus.ALIVE.to_wire() == "alive"
    assert NodeStatus.SUSPECTED.to_wire() == "suspected"
    assert NodeStatus.DEAD.to_wire() == "dead"

    assert NodeStatus.from_wire("alive") is NodeStatus.ALIVE
    assert NodeStatus.from_wire("suspected") is NodeStatus.SUSPECTED
    assert NodeStatus.from_wire("dead") is NodeStatus.DEAD
