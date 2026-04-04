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
from membership.results import UpsertPeerOutcome
from protocol.contracts import MembershipField
from protocol.message import Message
from protocol.message_types import MessageType
from utils.logging import get_logger
from utils.typing import JsonObject, JsonValue, JoinRequestPayload, LoggerLike, SenderLike


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

        node_id = payload.get(MembershipField.NODE_ID.value)
        host = payload.get(MembershipField.HOST.value)
        port = payload.get(MembershipField.PORT.value)

        if not isinstance(node_id, str) or node_id == "":
            log.warning("Invalid JOIN_REQUEST payload")
            return
        if not isinstance(host, str) or host == "":
            log.warning("Invalid JOIN_REQUEST payload")
            return
        if not isinstance(port, int):
            log.warning("Invalid JOIN_REQUEST payload")
            return

        join_payload: JoinRequestPayload = {
            MembershipField.NODE_ID.value: node_id,
            MembershipField.HOST.value: host,
            MembershipField.PORT.value: port,
        }

        if join_payload[MembershipField.NODE_ID.value] == self_node_id:
            return

        upsert_result = peer_table.upsert_peer(
            node_id=node_id,
            host=host,
            port=port,
        )

        if upsert_result.outcome is UpsertPeerOutcome.INSERTED:
            discovered_peer = upsert_result.peer
            if discovered_peer is not None:
                log.info(f"New peer joined: {node_id} {host}:{port}")
                _notify_discovered(discovered_peer)
        else:
            log.info(f"JOIN_REQUEST from known peer: {node_id}")

        peers_payload: list[JsonValue] = [
            {
                MembershipField.NODE_ID.value: p.node_id,
                MembershipField.HOST.value: p.host,
                MembershipField.PORT.value: p.port,
            }
            for p in peer_table.snapshot()
        ]
        reply_payload: JsonObject = {MembershipField.PEERS.value: peers_payload}

        reply = Message(
            msg_type=MessageType.PEER_LIST,
            sender_id=self_node_id,
            payload=reply_payload,
        )
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
        peers = msg.payload.get(MembershipField.PEERS.value)
        if not isinstance(peers, list):
            log.warning("Invalid PEER_LIST payload")
            return

        validated_peers: list[Peer] = []
        for entry in peers:
            if not isinstance(entry, dict):
                continue

            node_id = entry.get(MembershipField.NODE_ID.value)
            host = entry.get(MembershipField.HOST.value)
            port = entry.get(MembershipField.PORT.value)

            if not isinstance(node_id, str) or node_id == "":
                continue
            if not isinstance(host, str) or host == "":
                continue
            if not isinstance(port, int):
                continue

            validated_peers.append(Peer.new(node_id=node_id, host=host, port=port))

        merge_result = peer_table.merge_membership_view(validated_peers)
        for discovered_peer in merge_result.added:
            _notify_discovered(discovered_peer)

        if merge_result.added:
            log.info(f"Integrated {len(merge_result.added)} new peers from PEER_LIST")

    return handle_join_request, handle_peer_list
