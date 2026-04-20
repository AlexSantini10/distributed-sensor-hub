"""Validate runtime peer-registry behavior around transport runtime errors."""

import pytest

from runtime.networking import ClientPeerRegistry


class _AlwaysStoppedClient:
    """Model a transport client that has already been stopped."""

    def add_peer(self, peer: object) -> None:
        raise RuntimeError("TcpClient is stopped")

    def registered_peer_ids(self) -> tuple[str, ...]:
        return ()


class _AlreadyExistsClient:
    """Model a transport client that reports duplicate peer registration."""

    def add_peer(self, peer: object) -> None:
        raise RuntimeError("Peer already exists: node-b")

    def registered_peer_ids(self) -> tuple[str, ...]:
        return ()


class _RegisteredPeerClient:
    """Model a transport client that already has registered peers."""

    def add_peer(self, peer: object) -> None:
        return

    def registered_peer_ids(self) -> tuple[str, ...]:
        return ("node-z",)


def test_ensure_peer_propagates_stopped_client_error() -> None:
    """Assert stopped-client runtime errors are propagated to callers."""
    registry = ClientPeerRegistry(client=_AlwaysStoppedClient())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="stopped"):
        registry.ensure_peer(node_id="node-b", host="127.0.0.1", port=9001)

    assert registry.connected_peer_ids() == ()


def test_ensure_peer_tolerates_duplicate_registration_error() -> None:
    """Assert duplicate-registration runtime errors are treated as non-fatal."""
    registry = ClientPeerRegistry(client=_AlreadyExistsClient())  # type: ignore[arg-type]

    registry.ensure_peer(node_id="node-b", host="127.0.0.1", port=9001)

    assert registry.connected_peer_ids() == ("node-b",)


def test_connected_peer_ids_includes_client_registered_ids() -> None:
    """Assert peer snapshots include peers already tracked by the transport client."""
    registry = ClientPeerRegistry(client=_RegisteredPeerClient())  # type: ignore[arg-type]

    assert registry.connected_peer_ids() == ("node-z",)
