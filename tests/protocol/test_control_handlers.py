"""Validate protocol control-message handlers are non-fatal."""

from protocol.factory import build_ack, build_error
from runtime.protocol_assembly import setup_protocol


def _send(_peer_id: str, _msg: object) -> None:
    """Provide a no-op send callback for protocol wiring tests."""
    return


def test_error_message_is_handled_without_exception() -> None:
    """Assert that inbound ``ERROR`` messages do not crash dispatch."""
    dispatcher, _ = setup_protocol(
        self_node_id="node-local",
        send_function=_send,
    )

    msg = build_error(
        sender_id="node-remote",
        reason="simulated_error",
    )

    dispatcher.dispatch(msg)


def test_ack_message_is_handled_without_exception() -> None:
    """Assert that inbound ``ACK`` messages do not crash dispatch."""
    dispatcher, _ = setup_protocol(
        self_node_id="node-local",
        send_function=_send,
    )

    msg = build_ack(
        sender_id="node-remote",
        acked_type="PING",
    )

    dispatcher.dispatch(msg)
