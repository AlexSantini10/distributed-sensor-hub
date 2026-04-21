"""Provide transport-agnostic cluster introspection snapshots."""

from __future__ import annotations

from collections import deque
import threading
import time

from utils.typing import JsonObject, MembershipSnapshotDict, NodeSnapshot, ReplicationDeltaBatch


class ControlPlaneEventStore:
    """Keep a bounded in-memory history of protocol/control-plane events."""

    def __init__(self, *, max_events: int = 256) -> None:
        """Initialize a bounded event buffer with thread-safe access."""
        if max_events <= 0:
            raise ValueError("max_events must be > 0")
        self._lock = threading.Lock()
        self._events: deque[JsonObject] = deque(maxlen=max_events)

    def add_event(
        self,
        *,
        event_type: str,
        category: str,
        sender_id: str | None = None,
        target_id: str | None = None,
        details: JsonObject | None = None,
    ) -> None:
        """Append one event entry with deterministic required fields."""
        if not isinstance(event_type, str) or event_type == "":
            return
        if not isinstance(category, str) or category == "":
            return
        event: JsonObject = {
            "ts_ms": int(time.time() * 1000),
            "event_type": event_type,
            "category": category,
        }
        if isinstance(sender_id, str) and sender_id != "":
            event["sender_id"] = sender_id
        if isinstance(target_id, str) and target_id != "":
            event["target_id"] = target_id
        if isinstance(details, dict):
            event["details"] = dict(details)
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[JsonObject, ...]:
        """Return ordered events from oldest to newest."""
        with self._lock:
            return tuple(dict(item) for item in self._events)


class ReplicationGossipMetricsStore:
    """Track reusable counters for replication and gossip activity."""

    def __init__(self) -> None:
        """Initialize thread-safe counters for gossip and replication metrics."""
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {
            "gossip_messages_received_total": 0,
            "gossip_messages_sent_total": 0,
            "sensor_updates_applied_total": 0,
            "sensor_updates_pushed_total": 0,
            "get_delta_requests_received_total": 0,
            "get_delta_requests_sent_total": 0,
            "get_delta_unavailable_total": 0,
            "full_sync_requests_received_total": 0,
            "full_sync_requests_sent_total": 0,
            "full_sync_responses_received_total": 0,
            "full_sync_responses_sent_total": 0,
            "replication_rounds_total": 0,
        }

    def increment(self, key: str, amount: int = 1) -> None:
        """Increment one metric counter if registered."""
        if not isinstance(key, str) or key == "":
            return
        if not isinstance(amount, int) or amount <= 0:
            return
        with self._lock:
            if key not in self._counters:
                return
            self._counters[key] += amount

    def snapshot(self) -> JsonObject:
        """Return a stable metrics mapping."""
        with self._lock:
            return dict(sorted(self._counters.items(), key=lambda item: item[0]))


class ClusterIntrospectionService:
    """Build stable read-only introspection snapshots for any transport."""

    _SCHEMA_VERSION = "introspection/v1"

    def __init__(
        self,
        *,
        state_provider,
        membership_provider,
        topology_provider,
        replication_stats_provider,
        control_plane_events: ControlPlaneEventStore,
        replication_metrics: ReplicationGossipMetricsStore,
    ) -> None:
        """Store provider callables and backing stores used for snapshots."""
        self._state_provider = state_provider
        self._membership_provider = membership_provider
        self._topology_provider = topology_provider
        self._replication_stats_provider = replication_stats_provider
        self._control_plane_events = control_plane_events
        self._replication_metrics = replication_metrics

    def _stamp(self) -> JsonObject:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "generated_at_ms": int(time.time() * 1000),
        }

    def topology_snapshot(self) -> JsonObject:
        """Return the merged global topology view snapshot."""
        payload = self._topology_provider()
        response = self._stamp()
        response["topology"] = payload if isinstance(payload, dict) else {}
        return response

    def membership_snapshot(self) -> JsonObject:
        """Return membership snapshot with phi only for directly observed peers."""
        raw: MembershipSnapshotDict = self._membership_provider()
        peers_out: list[JsonObject] = []
        for peer in raw.get("peers", []):
            row: JsonObject = dict(peer)
            if row.get("direct_observed") is not True:
                row["phi"] = None
            peers_out.append(row)
        response = self._stamp()
        response["membership"] = {
            "local_node_id": raw.get("local_node_id", ""),
            "peers": peers_out,
        }
        return response

    def sensor_state_snapshot(self) -> JsonObject:
        """Return replicated sensor state in a stable flat record list."""
        raw: NodeSnapshot = self._state_provider()
        records: list[JsonObject] = []
        for node_id in sorted(raw.keys()):
            per_node = raw.get(node_id)
            if not isinstance(per_node, dict):
                continue
            for global_sensor_id in sorted(per_node.keys()):
                record = per_node.get(global_sensor_id)
                if not isinstance(record, dict):
                    continue
                sensor_id = global_sensor_id
                if isinstance(global_sensor_id, str) and ":" in global_sensor_id:
                    _, sensor_id = global_sensor_id.split(":", 1)
                records.append(
                    {
                        "global_sensor_id": global_sensor_id,
                        "sensor_id": sensor_id,
                        "origin": record.get("origin"),
                        "ts_ms": record.get("ts_ms"),
                        "value": record.get("value"),
                        "meta": record.get("meta", {}),
                    }
                )
        response = self._stamp()
        response["sensor_state"] = {
            "record_count": len(records),
            "records": records,
        }
        return response

    def recent_events_snapshot(self) -> JsonObject:
        """Return bounded recent control-plane/protocol events."""
        response = self._stamp()
        events = list(self._control_plane_events.snapshot())
        response["events"] = {
            "count": len(events),
            "items": events,
        }
        return response

    def replication_gossip_metrics_snapshot(self) -> JsonObject:
        """Return replication/gossip counters and state-watermark metrics."""
        response = self._stamp()
        state_stats = self._replication_stats_provider()
        if not isinstance(state_stats, dict):
            state_stats = {}
        response["metrics"] = {
            "counters": self._replication_metrics.snapshot(),
            "state_replication": state_stats,
        }
        return response

    def cluster_snapshot(self) -> JsonObject:
        """Return one aggregate snapshot across all introspection surfaces."""
        response = self._stamp()
        response["cluster"] = {
            "topology": self.topology_snapshot().get("topology", {}),
            "membership": self.membership_snapshot().get("membership", {}),
            "sensor_state": self.sensor_state_snapshot().get("sensor_state", {}),
            "events": self.recent_events_snapshot().get("events", {}),
            "metrics": self.replication_gossip_metrics_snapshot().get("metrics", {}),
        }
        return response
