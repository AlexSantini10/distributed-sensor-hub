"""Validate bootstrap peer handling does not pollute membership state."""

from membership.peer_table import PeerTable
from networking.tcp_client import Peer as TcpPeer
from runtime.networking import seed_peer_table


class DummyLog:
    """Provide the minimal logger interface used by networking helpers."""

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

    def demo(self, *args: object, **kwargs: object) -> None:
        pass


def test_seed_peer_table_ignores_bootstrap_placeholder_ids() -> None:
    """Assert bootstrap@host:port placeholders are never inserted into membership."""
    table = PeerTable(self_node_id="node-a")
    peers = [
        TcpPeer(node_id="bootstrap@127.0.0.1:9001", host="127.0.0.1", port=9001),
    ]

    seed_peer_table(peer_table=table, bootstrap_peers=peers, log=DummyLog())

    assert table.snapshot() == ()
