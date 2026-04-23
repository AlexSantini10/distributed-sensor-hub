"""Publish locally originated state updates to cluster peers."""

import math
import random
import threading
from typing import Callable, Protocol, cast

from networking.tcp_client import Peer as TcpPeer
from protocol.factory import build_get_delta, build_sensor_update
from protocol.message import Message
from protocol.messages import SensorMeta
from utils.typing import (
    JsonObject,
    LoggerLike,
    ReplicationDeltaBatch,
)


class PublisherPeerLike(Protocol):
    """Define the peer shape used by push-pull peer selection."""

    node_id: str
    host: str
    port: int


class PublisherPeerTableLike(Protocol):
    """Define the minimum membership surface used by the publisher."""

    def snapshot(self) -> tuple[object, ...]:
        """Return a snapshot of peers considered for replication."""
        ...


class ReplicationDeltaSourceLike(Protocol):
    """Define the minimum state-worker surface used by the publisher."""

    def pop_replication_deltas(self) -> ReplicationDeltaBatch:
        """Return ordered replication deltas to publish."""
        ...


class SensorUpdatePublisher(threading.Thread):
    """Run push-pull replication rounds over the current peer set."""

    def __init__(
        self,
        self_node_id: str,
        peer_table: PublisherPeerTableLike,
        tcp_client: "TcpClientLike",
        state_worker: ReplicationDeltaSourceLike,
        log: LoggerLike,
        interval_s: float = 1.0,
        push_ratio: float = 0.3,
        push_min_peers: int = 2,
        pull_ratio: float = 0.15,
        pull_min_peers: int = 1,
        pull_every_rounds: int = 3,
        pull_response_tracker: "PullResponseTrackerLike | None" = None,
        on_protocol_event: (
            Callable[[str, str | None, str | None, JsonObject | None], None] | None
        ) = None,
        on_metric: Callable[[str, int], None] | None = None,
        random_seed: int | None = None,
    ) -> None:
        """Initialize the publisher thread.

        Args:
            self_node_id (str): Local node id used as sender and local-origin filter.
            peer_table (PublisherPeerTableLike): Membership snapshot provider for replication targets.
            tcp_client (TcpClientLike): Outbound transport used to send protocol messages.
            state_worker (ReplicationDeltaSourceLike): State source used for deltas and pull cursors.
            log (LoggerLike): Logger used for transport and runtime failures.
            interval_s (float): Seconds between replication rounds.
            push_ratio (float): Push fanout ratio over alive peers.
            push_min_peers (int): Minimum push fanout per round.
            pull_ratio (float): Pull fanout ratio over alive peers.
            pull_min_peers (int): Minimum pull fanout per pull round.
            pull_every_rounds (int): Pull cadence in rounds.
            pull_response_tracker (PullResponseTrackerLike | None): Optional tracker
                that marks outbound pull requests to classify inbound updates.
            random_seed (int | None): Optional deterministic seed for peer sampling.

        Returns:
            None: This constructor configures the background publisher.
        """
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
        self._pull_response_tracker = pull_response_tracker
        self._on_protocol_event = on_protocol_event
        self._on_metric = on_metric
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
        if self._on_metric is not None:
            self._on_metric("replication_rounds_total", 1)
        peers = self._alive_peers()
        if not peers:
            return
        self._push_deltas(peers)
        if self._round % self._pull_every_rounds == 0:
            self._pull_missing_deltas(peers)

    def _alive_peers(self) -> tuple[PublisherPeerLike, ...]:
        """Return peers currently eligible for push-pull replication."""
        all_peers = self._peer_table.snapshot()
        eligible: list[PublisherPeerLike] = []
        for peer in all_peers:
            if (
                not hasattr(peer, "node_id")
                or not hasattr(peer, "host")
                or not hasattr(peer, "port")
            ):
                continue
            typed_peer = cast(PublisherPeerLike, peer)
            status = getattr(peer, "status", None)
            if status is None:
                eligible.append(typed_peer)
                continue
            if str(status).lower() == "alive":
                eligible.append(typed_peer)
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
        peers: tuple[PublisherPeerLike, ...],
        *,
        ratio: float,
        min_peers: int,
    ) -> tuple[PublisherPeerLike, ...]:
        """Select one random subset according to ratio and minimum fanout."""
        if not peers:
            return ()
        k = self._fanout_count(total=len(peers), ratio=ratio, min_peers=min_peers)
        if k >= len(peers):
            return peers
        return tuple(self._rng.sample(list(peers), k))

    def _push_deltas(self, peers: tuple[PublisherPeerLike, ...]) -> None:
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
                seq=update.get("seq") if isinstance(update.get("seq"), int) else None,
            )

            for target in push_targets:
                sent = self._send_message_to_peer(target, msg, op_name="SENSOR_UPDATE")
                if not sent:
                    continue
                if self._on_metric is not None:
                    self._on_metric("sensor_updates_pushed_total", 1)
                if self._on_protocol_event is not None:
                    self._on_protocol_event(
                        "sensor_update_sent",
                        self._self_node_id,
                        target.node_id,
                        {
                            "sensor_id": sensor_id,
                            "seq": update.get("seq"),
                        },
                    )

    def _pull_missing_deltas(self, peers: tuple[PublisherPeerLike, ...]) -> None:
        """Pull missing deltas from a random peer subset."""
        pull_targets = self._select_random_peers(
            peers,
            ratio=self._pull_ratio,
            min_peers=self._pull_min_peers,
        )
        for target in pull_targets:
            from_seq = -1
            if self._pull_response_tracker is not None:
                from_seq = self._pull_response_tracker.get_last_seq_for_peer(target.node_id)
            request = build_get_delta(
                sender_id=self._self_node_id,
                from_seq=from_seq,
            )
            sent = self._send_message_to_peer(target, request, op_name="GET_DELTA")
            if sent and self._pull_response_tracker is not None:
                self._pull_response_tracker.mark_pull_requested(target.node_id)
            if sent and self._on_metric is not None:
                self._on_metric("get_delta_requests_sent_total", 1)
            if sent and self._on_protocol_event is not None:
                self._on_protocol_event(
                    "get_delta_requested",
                    self._self_node_id,
                    target.node_id,
                    {"from_seq": from_seq},
                )

    def _send_message_to_peer(
        self,
        peer: PublisherPeerLike,
        msg: Message,
        *,
        op_name: str,
    ) -> bool:
        """Deliver one replication message to one peer using best-effort transport.

        Args:
            peer (PeerLike): Target peer descriptor.
            msg (Message): Protocol message to send.
            op_name (str): Human-readable operation label for logs.

        Returns:
            bool: ``True`` when delivery succeeds, else ``False``.
        """
        try:
            self._client.send_json(peer.node_id, msg)
            return True
        except KeyError:
            pass
        except Exception:
            self._log.warning(
                f"Failed to send {op_name} to peer_id={peer.node_id}",
                exc_info=True,
            )
            return False

        try:
            tcp_peer = TcpPeer(node_id=peer.node_id, host=peer.host, port=peer.port)
            self._client.add_peer(tcp_peer)
            self._client.send_json(peer.node_id, msg)
            return True
        except Exception:
            self._log.warning(
                f"Failed to add/connect peer_id={peer.node_id} for {op_name}",
                exc_info=True,
            )
            return False


class TcpClientLike(Protocol):
    """Define the outbound-client behavior used by the publisher."""

    def send_json(self, peer_id: str, obj: Message) -> None:
        """Send a message to a peer."""
        ...

    def add_peer(self, peer: TcpPeer) -> None:
        """Register a peer with the outbound client."""
        ...


class PullResponseTrackerLike(Protocol):
    """Define the pull tracking behavior used by the publisher."""

    def mark_pull_requested(self, peer_id: str, *, window_s: float | None = None) -> None:
        """Record that ``GET_DELTA`` has been requested from ``peer_id``."""
        ...

    def get_last_seq_for_peer(self, peer_id: str) -> int:
        """Return the latest pull cursor known for ``peer_id``."""
        ...
