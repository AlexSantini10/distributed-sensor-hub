# Failure Detection Module

`fd` contains the phi-accrual failure detector used by the node to estimate peer liveness continuously, instead of relying on fixed timeouts.
Its core engine is `HeartbeatMonitor`, which records heartbeat arrivals, tracks inter-arrival samples, computes `phi` as silence grows, and classifies peer liveness as `alive`, `suspected`, or `dead`. The module is primarily consumed by `PeerTable` and, through it, by heartbeat protocol handlers and the runtime heartbeat loop.

## Responsibilities

- Track heartbeat arrivals per peer with thread-safe access.
- Keep a bounded sliding window of inter-arrival intervals.
- Compute `phi` from elapsed time since the last heartbeat.
- Classify peers as `alive`, `suspected`, or `dead` using configurable thresholds.
- Expose a pluggable contract (`PhiEstimator`) for custom statistical models.

## Module Files

| File | Role |
|------|-------|
| `heartbeat.py` | `HeartbeatMonitor`, output dataclasses, and phi classification logic. |
| `phi_estimator.py` | `PhiEstimator` protocol and `ExponentialPhiEstimator` implementation. |
| `__init__.py` | Public module exports. |

## Public API

Exports from `fd`:

- `HeartbeatMonitor`
- `HeartbeatObservation`
- `PhiEvaluation`
- `PhiEstimator`
- `ExponentialPhiEstimator`

### `HeartbeatMonitor`

Constructor parameters:

- `max_intervals_per_peer` (default `128`)
- `threshold_suspect` (default `3.0`)
- `threshold_dead` (default `8.0`)
- `initial_interval_s` (default `1.0`)
- `phi_estimator` (default `ExponentialPhiEstimator`)

Main methods:

- `initialize_peer(peer_id, observed_at_s=None)`: seeds detector state for a discovered peer.
- `record_heartbeat(peer_id, arrived_at_s=None, sender_timestamp_ms=None)`: records one heartbeat, updates interval history, and returns `HeartbeatObservation` (always `alive` at receipt time).
- `evaluate_peer(peer_id, observed_at_s=None)`: computes current `phi` and returns `PhiEvaluation`.
- `evaluate_all(observed_at_s=None)`: computes state for all peers currently tracked by the detector.
- `remove_peer(peer_id)`: removes detector state for one peer.
- `get_intervals(peer_id)`: returns a read-only snapshot of observed intervals.
- `classify_phi(phi)`: maps `phi` to `NodeStatus`.

## Default Phi Model

`ExponentialPhiEstimator` uses an exponential model over heartbeat inter-arrival times:

- estimates `mean_interval_s` from observed samples;
- anchors the mean to `initial_interval_s` (baseline) to avoid overly aggressive phi after a few very short arrivals;
- computes survival `P(T > t)` and then `phi = -log10(P(T > t))`.

In practice: the longer a peer stays silent, the higher `phi` becomes.

## Project Integration

The `fd` module is used by `membership/peer_table.py`, which embeds `HeartbeatMonitor` and exposes FD outcomes to the rest of the node:

- on peer discovery/upsert: `initialize_peer(...)`;
- on incoming `PING/PONG`: `record_heartbeat(...)` and immediate reset to `alive`;
- in the heartbeat loop (`runtime/heartbeat.py`): `evaluate_failure_detector(...)` applies `alive/suspected/dead` transitions.

Results are exposed through `GET /api/membership`, with fields like `status`, `phi`, `sample_count`, and `sample_window_size`.

## Runtime Configuration

Environment variables (`utils/config.py`):

- `PHI_THRESHOLD_SUSPECT` (default `3.0`)
- `PHI_THRESHOLD_DEAD` (default `8.0`)
- `PHI_INITIAL_INTERVAL_S` (default `1.0`)

Constraints:

- `PHI_THRESHOLD_DEAD >= PHI_THRESHOLD_SUSPECT`
- `PHI_INITIAL_INTERVAL_S > 0`

## Extensibility

To use a custom model, implement the `PhiEstimator` protocol:

```python
class MyPhiEstimator:
    def compute_phi(self, *, elapsed_s: float, intervals_s: tuple[float, ...], initial_interval_s: float) -> float:
        ...
```

Then pass it to `HeartbeatMonitor(phi_estimator=MyPhiEstimator())`.

## Relevant Tests

- `tests/fd/test_heartbeat_monitor_di.py`: validates estimator dependency inversion.
- `tests/membership/test_peer_table.py`: validates `alive -> suspected -> dead -> alive` transitions, concurrency behavior, and membership snapshots with `phi`.
