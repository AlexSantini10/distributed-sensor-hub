"""Validate protocol-message decoding error handling.

Responsibilities:
    - Assert that malformed JSON payloads are rejected with ``ValueError``.
"""

import pytest

from protocol.message import Message


@pytest.mark.protocol
def test_from_json_missing_type() -> None:
    """Assert that messages without a type field are rejected.

    Returns:
        None: This test asserts required-field validation.
    """
    with pytest.raises(ValueError):
        Message.from_json({"sender_id": "n1"})


@pytest.mark.protocol
def test_from_json_invalid_type() -> None:
    """Assert that unknown message types are rejected.

    Returns:
        None: This test asserts message-type validation.
    """
    with pytest.raises(ValueError):
        Message.from_json({"type": "NOPE", "sender_id": "n1"})


@pytest.mark.protocol
def test_from_json_missing_sender_id() -> None:
    """Assert that messages without a sender identifier are rejected.

    Returns:
        None: This test asserts sender-id validation.
    """
    with pytest.raises(ValueError):
        Message.from_json({"type": "PING"})
