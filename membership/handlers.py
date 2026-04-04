"""Handle membership messages used for peer discovery and convergence.

Responsibilities:
    - Build join and peer-list handlers bound to a shared membership table.
    - Apply additive, idempotent membership updates from bootstrap and gossip.
    - Reply with the local peer view so discovery can converge across nodes.
    - Notify runtime code when membership learns a previously unknown peer.
"""

from collections.abc import Callable

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import build_peer_list
from protocol.message import Message
from protocol.messages import JoinRequestPayload, PeerDescriptor, PeerListPayload
from utils.logging import get_logger
from utils.typing import LoggerLike, SenderLike


OnPeerDiscovered = Callable[[Peer], None]


def make_membership_handlers(
    peer_table: PeerTable,
    send: SenderLike,
    self_node_id: str,
    on_peer_discovered: OnPeerDiscovered | None = None,
) -> tuple[Callable[[Message], None], Callable[[Message], None]]:
    """Create handlers for join and peer-list membership messages.

    Args:
        peer_table (PeerTable): Shared membership table updated by both handlers.
        send (SenderLike): Transport callback used to send protocol messages to a peer ID.
        self_node_id (str): Logical identifier of the local node.
        on_peer_discovered (OnPeerDiscovered | None): Optional callback invoked
            only when a previously unknown peer is inserted into ``peer_table``.

    Returns:
        tuple[Callable[[Message], None], Callable[[Message], None]]: Pair of
            handlers for ``JOIN_REQUEST`` and ``PEER_LIST`` messages.
    """
    log: LoggerLike = get_logger(__name__, self_node_id)

    def _notify_discovered(peer: Peer) -> None:
        """Invoke the discovery callback for a newly learned peer.

        Args:
            peer (Peer): Peer that was inserted into the membership table.

        Returns:
            None: This helper emits side effects only through the callback.
        """
        if on_peer_discovered is None:
            return

        try:
            on_peer_discovered(peer)
        except Exception:
            log.warning(
                f"on_peer_discovered failed for peer {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )

    def handle_join_request(msg: Message) -> None:
        """Process a join request and reply with the current peer list.

        Args:
            msg (Message): Incoming ``JOIN_REQUEST`` message whose payload must
                contain ``node_id``, ``host``, and ``port``.

        Returns:
            None: The handler updates membership state and may emit a reply.
        """
        payload = msg.payload
        if not isinstance(payload, JoinRequestPayload):
            log.warning("Invalid JOIN_REQUEST payload")
            return

        if payload.node_id == self_node_id:
            return

        upsert_result = peer_table.upsert_peer(
            node_id=payload.node_id,
            host=payload.host,
            port=payload.port,
        )

        if upsert_result.inserted:
            discovered_peer = upsert_result.peer
            if discovered_peer is not None:
                log.info(
                    f"New peer joined: {payload.node_id} {payload.host}:{payload.port}"
                )
                _notify_discovered(discovered_peer)
        else:
            log.info(
                "JOIN_REQUEST from known peer: "
                f"{payload.node_id} changed={upsert_result.changed} reason={upsert_result.reason}"
            )

        peers_payload = [
            PeerDescriptor(node_id=p.node_id, host=p.host, port=p.port)
            for p in peer_table.snapshot()
        ]
        reply = build_peer_list(sender_id=self_node_id, peers=peers_payload)
        send(msg.sender_id, reply)

    def handle_peer_list(msg: Message) -> None:
        """Merge peers from a peer-list message into local membership state.

        Args:
            msg (Message): Incoming ``PEER_LIST`` message whose payload must
                contain a ``peers`` list of dictionaries with ``node_id``, ``host``,
                and ``port``.

        Returns:
            None: The handler updates membership state in place.
        """
        payload = msg.payload
        if not isinstance(payload, PeerListPayload):
            log.warning("Invalid PEER_LIST payload")
            return

        validated_peers: list[Peer] = [
            Peer.new(node_id=entry.node_id, host=entry.host, port=entry.port)
            for entry in payload.peers
        ]

        merge_result = peer_table.merge_membership_view(validated_peers)
        for discovered_peer in merge_result.new_peers:
            _notify_discovered(discovered_peer)

        if merge_result.changed:
            log.info(
                "Integrated PEER_LIST updates: "
                f"merged={merge_result.merged_entries} "
                f"new={len(merge_result.new_peers)} "
                f"updated={len(merge_result.updated_peers)} "
                f"ignored={merge_result.ignored_entries}"
            )

    return handle_join_request, handle_peer_list
