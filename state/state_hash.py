"""Build deterministic hashes for replicated state snapshots."""

from __future__ import annotations

import hashlib
import json

from utils.typing import NodeSnapshot


def deterministic_state_hash(snapshot: NodeSnapshot) -> str:
    """Return a stable hash for semantically equivalent replicated state.

    The hash is based on sorted global sensor keys and non-volatile fields only.
    """
    normalized: list[dict[str, object]] = []
    for per_node in snapshot.values():
        if not isinstance(per_node, dict):
            continue
        for global_sensor_id, record in per_node.items():
            if not isinstance(record, dict):
                continue
            normalized.append(
                {
                    "sensor_id": global_sensor_id,
                    "value": record.get("value"),
                    "ts_ms": record.get("ts_ms"),
                    "origin": record.get("origin"),
                    "meta": {
                        "unit": (
                            record.get("meta", {}).get("unit")
                            if isinstance(record.get("meta"), dict)
                            else None
                        ),
                        "period_ms": (
                            record.get("meta", {}).get("period_ms")
                            if isinstance(record.get("meta"), dict)
                            else None
                        ),
                    },
                }
            )

    normalized.sort(key=lambda row: str(row["sensor_id"]))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
