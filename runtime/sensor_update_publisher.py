"""Publish locally originated state updates to cluster peers."""

import threading
from typing import Protocol

from networking.tcp_client import Peer as TcpPeer
from protocol.factory import build_sensor_update
from protocol.message import Message
from protocol.messages import SensorMeta
from utils.typing import (
    LoggerLike,
    PeerLike,
    PeerTableLike,
    ReplicationDeltaBatch,
    StateWorkerLike,
)


class SensorUpdatePublisher(threading.Thread):
    """Broadcast local winning updates to the membership peer set."""

    def __init__(
        self,
        self_node_id: str,
        peer_table: PeerTableLike,
        tcp_client: "TcpClientLike",
        state_worker: StateWorkerLike,
        log: LoggerLike,
        interval_s: float = 0.2,
    ) -> None:
        """Initialize the publisher thread."""
        super().__init__(daemon=True)

        self._self_node_id = self_node_id
        self._peer_table = peer_table
        self._client = tcp_client
        self._state_worker = state_worker
        self._log = log
        self._interval_s = interval_s

        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Request graceful publisher termination."""
        self._stop_event.set()
        if threading.current_thread() is self:
            return
        if self.ident is None:
            return
        self.join(timeout=2.0)

    def run(self) -> None:
        """Publish replication deltas until shutdown is requested."""
        while not self._stop_event.is_set():
            try:
                self._publish_once()
            except Exception:
                self._log.error("SensorUpdatePublisher failed", exc_info=True)

            self._stop_event.wait(timeout=self._interval_s)

    def _publish_once(self) -> None:
        """Publish one batch of local-origin winners to all known peers."""
        deltas: ReplicationDeltaBatch = self._state_worker.pop_replication_deltas()
        if not deltas:
            return

        peers = self._peer_table.snapshot()
        if not peers:
            return

        for update in deltas:
            origin = update.get("origin")
            if origin != self._self_node_id:
                continue

            sensor_id = update.get("sensor_id")
            if not isinstance(sensor_id, str) or sensor_id == "":
                continue

            meta_value = update.get("meta", {})
            meta: SensorMeta
            if isinstance(meta_value, dict):
                meta = SensorMeta(
                    unit=meta_value.get("unit"),
                    period_ms=meta_value.get("period_ms"),
                )
            else:
                meta = SensorMeta()

            msg = build_sensor_update(
                sender_id=self._self_node_id,
                sensor_id=sensor_id,
                value=update.get("value"),
                ts_ms=update.get("ts_ms"),
                origin=origin,
                meta=meta,
            )

            for p in peers:
                self._send_to_peer(p, msg)

    def _send_to_peer(self, peer: PeerLike, msg: Message) -> None:
        """Deliver one replication message to one peer using best-effort transport."""
        try:
            self._client.send_json(peer.node_id, msg)
            return
        except KeyError:
            pass
        except Exception:
            self._log.warning(
                f"Failed to send SENSOR_UPDATE to peer_id={peer.node_id}",
                exc_info=True,
            )
            return

        try:
            tcp_peer = TcpPeer(node_id=peer.node_id, host=peer.host, port=peer.port)
            self._client.add_peer(tcp_peer)
            self._client.send_json(peer.node_id, msg)
        except Exception:
            self._log.warning(
                f"Failed to add/connect peer_id={peer.node_id} for SENSOR_UPDATE",
                exc_info=True,
            )


class TcpClientLike(Protocol):
    """Define the outbound-client behavior used by the publisher."""

    def send_json(self, peer_id: str, obj: Message) -> None:
        """Send a message to a peer."""
        ...

    def add_peer(self, peer: TcpPeer) -> None:
        """Register a peer with the outbound client."""
        ...
