"""Publish locally originated state updates to cluster peers."""

import math
import random
import threading
from typing import Protocol

from networking.tcp_client import Peer as TcpPeer
from protocol.factory import build_get_delta, build_sensor_update
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
    """Run push-pull replication rounds over the current peer set."""

    def __init__(
        self,
        self_node_id: str,
        peer_table: PeerTableLike,
        tcp_client: "TcpClientLike",
        state_worker: StateWorkerLike,
        log: LoggerLike,
        interval_s: float = 1.0,
        push_ratio: float = 0.3,
        push_min_peers: int = 2,
        pull_ratio: float = 0.15,
        pull_min_peers: int = 1,
        pull_every_rounds: int = 3,
        random_seed: int | None = None,
    ) -> None:
        """Initialize the publisher thread."""
        super().__init__(daemon=True)
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        if not (0 <= push_ratio <= 1):
            raise ValueError("push_ratio must be between 0 and 1")
        if not (0 <= pull_ratio <= 1):
            raise ValueError("pull_ratio must be between 0 and 1")
        if push_min_peers < 0:
            raise ValueError("push_min_peers must be >= 0")
        if pull_min_peers < 0:
            raise ValueError("pull_min_peers must be >= 0")
        if pull_every_rounds <= 0:
            raise ValueError("pull_every_rounds must be > 0")

        self._self_node_id = self_node_id
        self._peer_table = peer_table
        self._client = tcp_client
        self._state_worker = state_worker
        self._log = log
        self._interval_s = interval_s
        self._push_ratio = push_ratio
        self._push_min_peers = push_min_peers
        self._pull_ratio = pull_ratio
        self._pull_min_peers = pull_min_peers
        self._pull_every_rounds = pull_every_rounds
        self._round = 0
        self._rng = random.Random(random_seed)

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
        """Run periodic push-pull replication rounds until shutdown."""
        while not self._stop_event.is_set():
            try:
                self._round += 1
                self._run_round()
            except Exception:
                self._log.error("SensorUpdatePublisher failed", exc_info=True)

            self._stop_event.wait(timeout=self._interval_s)

    def _run_round(self) -> None:
        """Run one push-pull replication round."""
        peers = self._alive_peers()
        if not peers:
            return
        self._push_deltas(peers)
        if self._round % self._pull_every_rounds == 0:
            self._pull_missing_deltas(peers)

    def _alive_peers(self) -> tuple[PeerLike, ...]:
        """Return peers currently eligible for push-pull replication."""
        all_peers = self._peer_table.snapshot()
        eligible: list[PeerLike] = []
        for peer in all_peers:
            status = getattr(peer, "status", None)
            if status is None:
                eligible.append(peer)
                continue
            if str(status).lower() == "alive":
                eligible.append(peer)
        return tuple(eligible)

    def _fanout_count(self, *, total: int, ratio: float, min_peers: int) -> int:
        """Return scalable fanout count using ratio with a floor."""
        if total <= 0:
            return 0
        by_ratio = int(math.ceil(ratio * total))
        desired = max(min_peers, by_ratio)
        if desired > total:
            return total
        return desired

    def _select_random_peers(
        self,
        peers: tuple[PeerLike, ...],
        *,
        ratio: float,
        min_peers: int,
    ) -> tuple[PeerLike, ...]:
        """Select one random subset according to ratio and minimum fanout."""
        if not peers:
            return ()
        k = self._fanout_count(total=len(peers), ratio=ratio, min_peers=min_peers)
        if k >= len(peers):
            return peers
        return tuple(self._rng.sample(list(peers), k))

    def _push_deltas(self, peers: tuple[PeerLike, ...]) -> None:
        """Push local-origin replication deltas to a random peer subset."""
        deltas: ReplicationDeltaBatch = self._state_worker.pop_replication_deltas()
        if not deltas:
            return

        push_targets = self._select_random_peers(
            peers,
            ratio=self._push_ratio,
            min_peers=self._push_min_peers,
        )
        if not push_targets:
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

            for target in push_targets:
                self._send_message_to_peer(target, msg, op_name="SENSOR_UPDATE")

    def _pull_missing_deltas(self, peers: tuple[PeerLike, ...]) -> None:
        """Pull missing deltas from a random peer subset."""
        pull_targets = self._select_random_peers(
            peers,
            ratio=self._pull_ratio,
            min_peers=self._pull_min_peers,
        )
        for target in pull_targets:
            since_ts_ms = self._state_worker.get_latest_timestamp_for_origin(target.node_id)
            request = build_get_delta(
                sender_id=self._self_node_id,
                since_ts_ms=since_ts_ms,
            )
            self._send_message_to_peer(target, request, op_name="GET_DELTA")

    def _send_message_to_peer(self, peer: PeerLike, msg: Message, *, op_name: str) -> None:
        """Deliver one replication message to one peer using best-effort transport."""
        try:
            self._client.send_json(peer.node_id, msg)
            return
        except KeyError:
            pass
        except Exception:
            self._log.warning(
                f"Failed to send {op_name} to peer_id={peer.node_id}",
                exc_info=True,
            )
            return

        try:
            tcp_peer = TcpPeer(node_id=peer.node_id, host=peer.host, port=peer.port)
            self._client.add_peer(tcp_peer)
            self._client.send_json(peer.node_id, msg)
        except Exception:
            self._log.warning(
                f"Failed to add/connect peer_id={peer.node_id} for {op_name}",
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
