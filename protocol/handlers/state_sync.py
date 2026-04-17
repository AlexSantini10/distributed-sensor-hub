"""Handle protocol messages that synchronize replicated state."""

from collections.abc import Callable
import time

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import (
    build_delta_unavailable,
    build_full_sync_request,
    build_full_sync_response,
    build_sensor_update,
)
from protocol.message import Message
from protocol.messages import (
    DeltaUnavailablePayload,
    FullSyncRequestPayload,
    FullSyncResponsePayload,
    GetDeltaPayload,
    PeerDescriptor,
    SensorMeta,
    SensorUpdatePayload,
)
from utils.logging import get_logger
from utils.typing import (
    LoggerLike,
    ReplicationDeltaSourceLike,
    SenderLike,
    StateWorkerLike,
)


def make_sensor_update_handler(
    state_worker: StateWorkerLike,
    self_node_id: str,
    peer_table: PeerTable | None = None,
) -> Callable[[Message], None]:
    """Create a handler for replicated sensor updates."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def handle_sensor_update(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, SensorUpdatePayload):
            log.warning("Invalid SENSOR_UPDATE payload")
            return

        try:
            applied = state_worker.merge_update(
                sensor_id=payload.sensor_id,
                value=payload.value,
                ts_ms=payload.ts_ms,
                origin=payload.origin,
                meta=payload.meta.to_mapping(),
            )
        except Exception:
            log.error("Failed to merge SENSOR_UPDATE", exc_info=True)
            return

        if applied:
            if peer_table is not None:
                peer_table.record_indirect_evidence(
                    payload.origin,
                    source="sensor_update",
                    observed_ts_ms=payload.ts_ms,
                )
            log.info(
                f"SENSOR_UPDATE applied: sensor={payload.sensor_id} origin={payload.origin} ts={payload.ts_ms}"
            )

    return handle_sensor_update


def handle_sensor_update(msg: Message) -> None:
    """Warn that sensor-update handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("SENSOR_UPDATE received but handler is not wired")


def make_full_sync_request_handler(
    state_worker: StateWorkerLike,
    peer_table: PeerTable,
    send: SenderLike,
    self_node_id: str,
) -> Callable[[Message], None]:
    """Create a handler that replies to full-sync requests with state and membership."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def handle_full_sync_request(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, FullSyncRequestPayload):
            log.warning("Invalid FULL_SYNC_REQUEST payload")
            return

        requester_id = payload.requester_id if payload.requester_id is not None else msg.sender_id
        if requester_id == "":
            requester_id = msg.sender_id

        state_snapshot = state_worker.get_state_snapshot()
        membership_snapshot = tuple(
            PeerDescriptor(node_id=peer.node_id, host=peer.host, port=peer.port)
            for peer in peer_table.snapshot()
        )

        response = build_full_sync_response(
            sender_id=self_node_id,
            state=state_snapshot,
            membership=membership_snapshot,
        )

        try:
            send(requester_id, response)
            log.info(
                f"FULL_SYNC_RESPONSE sent to {requester_id} "
                f"state_nodes={len(state_snapshot)} "
                f"membership_peers={len(membership_snapshot)}"
            )
        except Exception:
            log.warning(
                f"Failed to send FULL_SYNC_RESPONSE to {requester_id}",
                exc_info=True,
            )

    return handle_full_sync_request


def make_full_sync_response_handler(
    state_worker: StateWorkerLike,
    peer_table: PeerTable,
    self_node_id: str,
    on_peer_discovered: Callable[[Peer], None] | None = None,
) -> Callable[[Message], None]:
    """Create a handler that merges full state and membership snapshots."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def _notify_discovered(peer: Peer) -> None:
        if on_peer_discovered is None:
            return
        try:
            on_peer_discovered(peer)
        except Exception:
            log.warning(
                f"on_peer_discovered failed for peer {peer.node_id} {peer.host}:{peer.port}",
                exc_info=True,
            )

    def handle_full_sync_response(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, FullSyncResponsePayload):
            log.warning("Invalid FULL_SYNC_RESPONSE payload")
            return

        incoming_peers = [
            Peer.new(node_id=entry.node_id, host=entry.host, port=entry.port)
            for entry in payload.membership
        ]
        merge_result = peer_table.merge_membership_view(incoming_peers)
        for discovered in merge_result.new_peers:
            _notify_discovered(discovered)
        now_ms = 0
        for entry in payload.membership:
            if now_ms == 0:
                now_ms = int(time.time() * 1000)
            peer_table.record_indirect_evidence(
                entry.node_id,
                source="full_sync_membership",
                observed_ts_ms=now_ms,
            )

        applied_updates = state_worker.merge_state(
            remote_full_state=payload.state,
            reject_partial=True,
        )
        for per_node in payload.state.values():
            if not isinstance(per_node, dict):
                continue
            for record in per_node.values():
                if not isinstance(record, dict):
                    continue
                origin = record.get("origin")
                ts_ms = record.get("ts_ms")
                if isinstance(origin, str) and origin != "" and isinstance(ts_ms, int):
                    peer_table.record_indirect_evidence(
                        origin,
                        source="full_sync_state",
                        observed_ts_ms=ts_ms,
                    )

        log.info(
            "FULL_SYNC_RESPONSE applied: "
            f"sender={msg.sender_id} "
            f"state_updates={applied_updates} "
            f"membership_merged={merge_result.merged_entries} "
            f"membership_new={len(merge_result.new_peers)} "
            f"membership_updated={len(merge_result.updated_peers)} "
            f"membership_ignored={merge_result.ignored_entries}"
        )

    return handle_full_sync_response


def make_delta_unavailable_handler(
    send: SenderLike,
    self_node_id: str,
) -> Callable[[Message], None]:
    """Create a handler that falls back to full sync when delta is unavailable."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def handle_delta_unavailable(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, DeltaUnavailablePayload):
            log.warning("Invalid DELTA_UNAVAILABLE payload")
            return

        request = build_full_sync_request(
            sender_id=self_node_id,
            requester_id=self_node_id,
        )
        try:
            send(msg.sender_id, request)
            log.info(
                "DELTA_UNAVAILABLE received; requested FULL_SYNC "
                f"from={msg.sender_id} reason={payload.reason}"
            )
        except Exception:
            log.warning(
                f"Failed to request FULL_SYNC from {msg.sender_id} after DELTA_UNAVAILABLE",
                exc_info=True,
            )

    return handle_delta_unavailable


def make_get_delta_handler(
    *,
    state_worker: ReplicationDeltaSourceLike,
    send: SenderLike,
    self_node_id: str,
) -> Callable[[Message], None]:
    """Create a handler that serves incremental deltas or fallback signals."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def handle_get_delta(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, GetDeltaPayload):
            log.warning("Invalid GET_DELTA payload")
            return

        requester_id = msg.sender_id
        deltas = state_worker.get_replication_deltas_since(
            since_ts_ms=payload.since_ts_ms
        )
        if deltas is None:
            unavailable = build_delta_unavailable(
                sender_id=self_node_id,
                reason="stale_cursor",
            )
            try:
                send(requester_id, unavailable)
                log.info(
                    "GET_DELTA unavailable: "
                    f"requester={requester_id} since_ts_ms={payload.since_ts_ms}"
                )
            except Exception:
                log.warning(
                    f"Failed to send DELTA_UNAVAILABLE to {requester_id}",
                    exc_info=True,
                )
            return

        sent_count = 0
        for delta in deltas:
            sensor_id = delta.get("sensor_id")
            origin = delta.get("origin")
            ts_ms = delta.get("ts_ms")
            if (
                not isinstance(sensor_id, str)
                or sensor_id == ""
                or not isinstance(origin, str)
                or origin == ""
                or not isinstance(ts_ms, int)
            ):
                continue

            try:
                message = build_sensor_update(
                    sender_id=self_node_id,
                    sensor_id=sensor_id,
                    value=delta.get("value"),
                    ts_ms=ts_ms,
                    origin=origin,
                    meta=SensorMeta.from_mapping(delta.get("meta", {})),
                )
                send(requester_id, message)
                sent_count += 1
            except Exception:
                log.warning(
                    f"Failed to send delta SENSOR_UPDATE to {requester_id}",
                    exc_info=True,
                )
                return

        log.info(
            "GET_DELTA served: "
            f"requester={requester_id} since_ts_ms={payload.since_ts_ms} "
            f"sent_updates={sent_count}"
        )

    return handle_get_delta


def handle_full_sync_request(msg: Message) -> None:
    """Warn that full-sync request handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("FULL_SYNC_REQUEST received but handler is not wired")


def handle_full_sync_response(msg: Message) -> None:
    """Warn that full-sync response handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("FULL_SYNC_RESPONSE received but handler is not wired")


def handle_delta_unavailable(msg: Message) -> None:
    """Warn that delta-unavailable handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("DELTA_UNAVAILABLE received but handler is not wired")


def handle_get_delta(msg: Message) -> None:
    """Warn that get-delta handling has not been wired for this node."""
    log = get_logger(__name__, msg.sender_id)
    log.warning("GET_DELTA received but handler is not wired")
