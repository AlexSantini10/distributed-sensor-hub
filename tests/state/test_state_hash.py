"""Validate deterministic hashing for replicated state snapshots."""

from state.state_hash import deterministic_state_hash


def test_state_hash_is_deterministic_across_key_order() -> None:
    """Assert equivalent state dictionaries yield the same deterministic hash."""
    snapshot_a = {
        "node-1": {
            "node-a:sensor-1": {
                "value": 1,
                "ts_ms": 100,
                "origin": "node-a",
                "meta": {"unit": "C", "period_ms": 1000},
            },
            "node-b:sensor-2": {
                "value": 2,
                "ts_ms": 200,
                "origin": "node-b",
                "meta": {"unit": "%", "period_ms": 1000},
            },
        }
    }
    snapshot_b = {
        "node-1": {
            "node-b:sensor-2": {
                "value": 2,
                "ts_ms": 200,
                "origin": "node-b",
                "meta": {"period_ms": 1000, "unit": "%"},
            },
            "node-a:sensor-1": {
                "value": 1,
                "ts_ms": 100,
                "origin": "node-a",
                "meta": {"period_ms": 1000, "unit": "C"},
            },
        }
    }

    assert deterministic_state_hash(snapshot_a) == deterministic_state_hash(snapshot_b)
