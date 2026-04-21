"""Maintain disseminated cluster topology with LWW per-node merge semantics.

Responsibilities:
    - Track one local topology declaration for this node's direct neighbors.
    - Merge remote topology declarations into an eventually consistent global view.
    - Expose a reusable adjacency-map snapshot independent from UI/demo layers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import threading
import time

from utils.typing import JsonObject


@dataclass(frozen=True, slots=True)
class TopologyEntry:
    """Represent one node's direct-neighbor declaration."""

    node_id: str
    direct_neighbors: tuple[str, ...]
    updated_at_ms: int

    def __post_init__(self) -> None:
        """Validate entry fields and normalize deterministic neighbor ordering."""
        if not isinstance(self.node_id, str) or self.node_id == "":
            raise ValueError("node_id must be a non-empty string")
        if not isinstance(self.updated_at_ms, int):
            raise ValueError("updated_at_ms must be an int")
        if self.updated_at_ms < 0:
            raise ValueError("updated_at_ms must be >= 0")

        cleaned: list[str] = []
        for neighbor in self.direct_neighbors:
            if not isinstance(neighbor, str) or neighbor == "":
                raise ValueError("direct_neighbors entries must be non-empty strings")
            if neighbor == self.node_id:
                continue
            cleaned.append(neighbor)

        normalized = tuple(sorted(set(cleaned)))
        object.__setattr__(self, "direct_neighbors", normalized)

    def to_mapping(self) -> JsonObject:
        """Serialize one topology entry for gossip payloads."""
        return {
            "node_id": self.node_id,
            "direct_neighbors": list(self.direct_neighbors),
            "updated_at_ms": self.updated_at_ms,
        }

    @classmethod
    def from_mapping(cls, raw: object) -> "TopologyEntry":
        """Build one validated topology entry from a raw JSON mapping."""
        if not isinstance(raw, dict):
            raise ValueError("topology entry must be an object")
        node_id = raw.get("node_id")
        updated_at_ms = raw.get("updated_at_ms")
        neighbors_raw = raw.get("direct_neighbors", [])
        if not isinstance(neighbors_raw, list):
            raise ValueError("direct_neighbors must be a list")
        return cls(
            node_id=str(node_id) if isinstance(node_id, str) else "",
            direct_neighbors=tuple(neighbors_raw),
            updated_at_ms=updated_at_ms if isinstance(updated_at_ms, int) else -1,
        )


class TopologyStateStore:
    """Store local and remote topology declarations with LWW merge behavior."""

    def __init__(
        self,
        *,
        self_node_id: str,
    ) -> None:
        """Initialize an empty topology store for one node."""
        if not isinstance(self_node_id, str) or self_node_id == "":
            raise ValueError("self_node_id must be a non-empty string")
        self._self_node_id = self_node_id
        self._lock = threading.Lock()
        self._entries: dict[str, TopologyEntry] = {}
        self._local_neighbors: set[str] = set()

    def set_local_neighbors(self, neighbors: Iterable[str]) -> TopologyEntry:
        """Publish a new local direct-neighbor declaration."""
        normalized = self._normalize_neighbors(neighbors)
        with self._lock:
            if normalized == self._local_neighbors and self._self_node_id in self._entries:
                return self._entries[self._self_node_id]
            self._local_neighbors = set(normalized)
            entry = TopologyEntry(
                node_id=self._self_node_id,
                direct_neighbors=tuple(sorted(self._local_neighbors)),
                updated_at_ms=self._next_local_version_locked(),
            )
            self._entries[self._self_node_id] = entry
            return entry

    def mark_neighbor_connected(self, node_id: str) -> TopologyEntry | None:
        """Add one direct neighbor to the local declaration."""
        if (
            node_id == self._self_node_id
            or node_id == ""
            or node_id.startswith("bootstrap@")
        ):
            return None
        with self._lock:
            if node_id in self._local_neighbors:
                return self._entries.get(self._self_node_id)
            self._local_neighbors.add(node_id)
            entry = TopologyEntry(
                node_id=self._self_node_id,
                direct_neighbors=tuple(sorted(self._local_neighbors)),
                updated_at_ms=self._next_local_version_locked(),
            )
            self._entries[self._self_node_id] = entry
            return entry

    def mark_neighbor_disconnected(self, node_id: str) -> TopologyEntry | None:
        """Remove one direct neighbor from the local declaration."""
        with self._lock:
            if node_id not in self._local_neighbors:
                return self._entries.get(self._self_node_id)
            self._local_neighbors.remove(node_id)
            entry = TopologyEntry(
                node_id=self._self_node_id,
                direct_neighbors=tuple(sorted(self._local_neighbors)),
                updated_at_ms=self._next_local_version_locked(),
            )
            self._entries[self._self_node_id] = entry
            return entry

    def merge_entry(self, entry: TopologyEntry) -> bool:
        """Merge one remote topology declaration via LWW per-node semantics."""
        with self._lock:
            current = self._entries.get(entry.node_id)
            if current is None:
                self._entries[entry.node_id] = entry
                return True
            if entry.updated_at_ms > current.updated_at_ms:
                self._entries[entry.node_id] = entry
                return True
            if entry.updated_at_ms < current.updated_at_ms:
                return False
            if entry.direct_neighbors > current.direct_neighbors:
                self._entries[entry.node_id] = entry
                return True
            return False

    def merge_entries(self, entries: Iterable[TopologyEntry]) -> int:
        """Merge multiple entries and return how many changed the local view."""
        changed = 0
        for entry in entries:
            changed += int(self.merge_entry(entry))
        return changed

    def get_adjacency_map(self) -> dict[str, tuple[str, ...]]:
        """Return a deterministic adjacency map snapshot."""
        with self._lock:
            node_ids = sorted(self._entries.keys())
            return {
                node_id: self._entries[node_id].direct_neighbors
                for node_id in node_ids
            }

    def snapshot_entries(self) -> tuple[TopologyEntry, ...]:
        """Return a deterministic snapshot of all known topology entries."""
        with self._lock:
            return tuple(
                self._entries[node_id]
                for node_id in sorted(self._entries.keys())
            )

    def build_gossip_state(self) -> JsonObject:
        """Build the serializable topology fragment embedded in gossip state."""
        entries = self.snapshot_entries()
        return {
            "topology": {
                "entries": [entry.to_mapping() for entry in entries]
            }
        }

    def topology_snapshot(self) -> JsonObject:
        """Return a reusable read-only topology snapshot for internal consumers."""
        adjacency = self.get_adjacency_map()
        entries = self.snapshot_entries()
        return {
            "local_node_id": self._self_node_id,
            "adjacency": {k: list(v) for k, v in adjacency.items()},
            "entries": [entry.to_mapping() for entry in entries],
        }

    def _next_local_version_locked(self) -> int:
        """Return a monotonic local version for the local topology declaration."""
        now_ms = int(time.time() * 1000)
        current = self._entries.get(self._self_node_id)
        if current is None:
            return now_ms
        if now_ms > current.updated_at_ms:
            return now_ms
        return current.updated_at_ms + 1

    def _normalize_neighbors(self, neighbors: Iterable[str]) -> set[str]:
        """Validate and normalize neighbor IDs before local publication."""
        normalized: set[str] = set()
        for node_id in neighbors:
            if not isinstance(node_id, str) or node_id == "":
                continue
            if node_id == self._self_node_id:
                continue
            if node_id.startswith("bootstrap@"):
                continue
            normalized.add(node_id)
        return normalized
