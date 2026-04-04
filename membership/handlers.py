"""Handle membership messages used for peer discovery and convergence.

Responsibilities:
    - Build join and peer-list handlers bound to a shared membership table.
    - Apply additive, idempotent membership updates from bootstrap and gossip.
    - Reply with the local peer view so discovery can converge across nodes.
    - Notify runtime code when membership learns a previously unknown peer.
"""

from collections.abc import Callable
from typing import TypeVar

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import build_peer_list
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.messages import JoinRequestPayload, PeerDescriptor, PeerListPayload
from utils.logging import get_logger
from utils.typing import LoggerLike, SenderLike


OnPeerDiscovered = Callable[[Peer], None]
PayloadT = TypeVar("PayloadT", JoinRequestPayload, PeerListPayload)


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

    def _format_status(status: object) -> str:
        if status is None:
            return "none"
        return str(status)

    def _format_transition(previous: object, new: object) -> str:
        return f"{_format_status(previous)}->{_format_status(new)}"

    def _extract_payload(
        *,
        msg: Message,
        expected_type: MessageType,
        payload_type: type[PayloadT],
    ) -> PayloadT | None:
        """Return the typed payload or reject the message consistently."""
        if msg.msg_type is not expected_type or not isinstance(msg.payload, payload_type):
            log.warning(
                "Rejected invalid membership message: "
                f"expected={expected_type.value} actual={msg.msg_type.value} "
                f"sender={msg.sender_id}"
            )
            return None
        return msg.payload

    def _build_peer_list_reply() -> Message:
        """Build a peer-list reply from a stable membership snapshot."""
        return build_peer_list(
            sender_id=self_node_id,
            peers=[
                PeerDescriptor(node_id=peer.node_id, host=peer.host, port=peer.port)
                for peer in peer_table.snapshot()
            ],
        )

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
            msg (Message): Incoming validated ``JOIN_REQUEST`` message whose
                payload must be ``JoinRequestPayload``.

        Returns:
            None: The handler updates membership state and may emit a reply.
        """
        payload = _extract_payload(
            msg=msg,
            expected_type=MessageType.JOIN_REQUEST,
            payload_type=JoinRequestPayload,
        )
        if payload is None:
            return

        if payload.node_id == self_node_id:
            log.info("Ignored self JOIN_REQUEST")
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
                    "Accepted JOIN_REQUEST: "
                    f"peer={payload.node_id} "
                    f"endpoint={payload.host}:{payload.port} "
                    f"transition={_format_transition(upsert_result.previous_status, upsert_result.new_status)} "
                    f"reason={upsert_result.reason}"
                )
                _notify_discovered(discovered_peer)
        else:
            log.info(
                "Processed duplicate JOIN_REQUEST: "
                f"peer={payload.node_id} "
                f"endpoint={payload.host}:{payload.port} "
                f"changed={upsert_result.changed} "
                f"transition={_format_transition(upsert_result.previous_status, upsert_result.new_status)} "
                f"reason={upsert_result.reason}"
            )

        reply = _build_peer_list_reply()
        try:
            send(msg.sender_id, reply)
        except Exception:
            log.warning(
                f"Failed to send PEER_LIST reply to {msg.sender_id}",
                exc_info=True,
            )
            raise

    def handle_peer_list(msg: Message) -> None:
        """Merge peers from a peer-list message into local membership state.

        Args:
            msg (Message): Incoming validated ``PEER_LIST`` message whose
                payload must be ``PeerListPayload``.

        Returns:
            None: The handler updates membership state in place.
        """
        payload = _extract_payload(
            msg=msg,
            expected_type=MessageType.PEER_LIST,
            payload_type=PeerListPayload,
        )
        if payload is None:
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
                f"ignored={merge_result.ignored_entries} "
                f"reason={merge_result.reason}"
            )
        else:
            log.info(
                "Ignored duplicate PEER_LIST: "
                f"merged=0 ignored={merge_result.ignored_entries} "
                f"reason={merge_result.reason}"
            )

    return handle_join_request, handle_peer_list
