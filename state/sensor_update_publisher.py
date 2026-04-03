"""Publish locally originated state updates to cluster peers.

Responsibilities:
    - Drain replication-only snapshots from the node state worker.
    - Convert winning LWW records into ``SENSOR_UPDATE`` protocol messages.
    - Best-effort fan out local-origin updates to every known peer.
    - Avoid immediate re-broadcast loops by skipping non-local winners.
"""

import threading
from typing import Any

from protocol.message import Message
from protocol.message_types import MessageType


class SensorUpdatePublisher(threading.Thread):
    """Broadcast local winning updates to the membership peer set.

    Attributes:
        _self_node_id (str): Local node identifier used to filter publishable winners.
        _peer_table (Any): Peer table providing the current replication target set.
        _client (Any): TCP client used to send protocol messages to peers.
        _state_worker (Any): State worker supplying replication-only incremental snapshots.
        _log (Any): Logger-like object used for error reporting.
        _interval_s (float): Delay between publish attempts.
        _stop_event (threading.Event): Shutdown signal checked by the publish loop.
    """

    def __init__(
        self,
        self_node_id: str,
        peer_table: Any,
        tcp_client: Any,
        state_worker: Any,
        log: Any,
        interval_s: float = 0.2,
    ) -> None:
        """Initialize the publisher thread.

        Args:
            self_node_id (str): Local node identifier used to filter local-origin winners.
            peer_table (Any): Peer table exposing ``list_peers()``.
            tcp_client (Any): Client exposing ``send_json()`` and ``add_peer()``.
            state_worker (Any): Worker exposing ``pop_replication_updates()``.
            log (Any): Logger-like object used for warnings and errors.
            interval_s (float): Delay between publish attempts in seconds.

        Returns:
            None: This constructor does not return a value.
        """
        super().__init__(daemon=True)

        self._self_node_id = self_node_id
        self._peer_table = peer_table
        self._client = tcp_client
        self._state_worker = state_worker
        self._log = log
        self._interval_s = interval_s

        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Request graceful publisher termination.

        Returns:
            None: This method only signals shutdown.
        """
        self._stop_event.set()

    def run(self) -> None:
        """Publish replication deltas until shutdown is requested.

        Returns:
            None: This method services the publish loop until stopped.
        """
        while not self._stop_event.is_set():
            try:
                self._publish_once()
            except Exception:
                self._log.error("SensorUpdatePublisher failed", exc_info=True)

            self._stop_event.wait(timeout=self._interval_s)

    def _publish_once(self) -> None:
        """Publish one batch of local-origin winners to all known peers.

        Returns:
            None: This method performs best-effort message delivery.
        """
        snapshot = self._state_worker.pop_replication_updates() or {}
        updates = snapshot.get(self._self_node_id, {}) or {}
        if not updates:
            return

        peers = self._peer_table.list_peers()
        if not peers:
            return

        for global_sensor_id, update in updates.items():
            origin = update.get("origin")
            if origin != self._self_node_id:
                continue

            sensor_id = global_sensor_id
            if isinstance(global_sensor_id, str) and ":" in global_sensor_id:
                sensor_id = global_sensor_id.split(":", 1)[1]

            msg = Message(
                msg_type=MessageType.SENSOR_UPDATE,
                sender_id=self._self_node_id,
                payload={
                    "sensor_id": sensor_id,
                    "value": update.get("value"),
                    "ts_ms": update.get("ts_ms"),
                    "origin": origin,
                    "meta": update.get("meta", {}),
                },
            )

            for p in peers:
                self._send_to_peer(p, msg)

    def _send_to_peer(self, peer: Any, msg: Message) -> None:
        """Deliver one replication message to one peer using best-effort transport.

        Args:
            peer (Any): Membership peer object exposing ``node_id``, ``host``, and ``port``.
            msg (Message): Protocol message describing a winning sensor update.

        Returns:
            None: This method performs best-effort delivery only.
        """
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
            from networking.tcp_client import Peer as TcpPeer

            tcp_peer = TcpPeer(node_id=peer.node_id, host=peer.host, port=peer.port)
            self._client.add_peer(tcp_peer)
            self._client.send_json(peer.node_id, msg)
        except Exception:
            self._log.warning(
                f"Failed to add/connect peer_id={peer.node_id} for SENSOR_UPDATE",
                exc_info=True,
            )
