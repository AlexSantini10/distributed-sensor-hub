# Module: fd

## Responsibility
Heartbeat-based phi-accrual failure detection for peer liveness. The module tracks heartbeat arrivals, computes a suspicion score (`phi`), and classifies peers as `alive`, `suspected`, or `dead`.

## How It Works
- For each peer, the detector stores the last heartbeat arrival time and a bounded window of recent inter-arrival intervals.
- At evaluation time, it computes:
  `phi = -log10(P(T > t))`
  where `t` is the elapsed time since the last heartbeat.
- The default estimator assumes an exponential distribution with:
  `lambda = 1 / mean_interval`
- `mean_interval` comes from the peer's recent heartbeat history, but is never allowed to go below `initial_interval_s`.

## Intuition
- `phi` is a suspicion score, not a fixed timeout.
- The detector asks: "Given this peer's usual heartbeat rhythm, how surprising is the current silence?"
- A peer that usually sends heartbeats every `1.0s` becomes suspicious after a shorter silence than a peer that usually sends them every `1.8s`.
- The detector measures heartbeat timing, not request/response latency.

## Standard Classification
- `phi < 3.0` -> `alive`
- `3.0 <= phi < 8.0` -> `suspected`
- `phi >= 8.0` -> `dead`

## Public API
### `HeartbeatMonitor`
- Tracks per-peer heartbeats and computes `phi`.
- Main methods:
  - `initialize_peer(...)`
  - `remove_peer(...)`
  - `record_heartbeat(...)`
  - `get_intervals(...)`
  - `evaluate_peer(...)`
  - `evaluate_all(...)`
  - `classify_phi(...)`
- Exposed properties:
  - `threshold_suspect`
  - `threshold_dead`
  - `max_intervals_per_peer`

### `HeartbeatObservation`
- Immutable result returned by `record_heartbeat(...)`.
- Fields: `peer_id`, `arrived_at_s`, `interval_s`, `sender_timestamp_ms`, `phi`, `status`.

### `PhiEvaluation`
- Immutable result returned by `evaluate_peer(...)` and `evaluate_all(...)`.
- Fields: `peer_id`, `phi`, `status`.

### `PhiEstimator`
- Protocol for pluggable phi computation.
- Method: `compute_phi(elapsed_s, intervals_s, initial_interval_s)`.

### `ExponentialPhiEstimator`
- Default `PhiEstimator` implementation based on exponential survival.

## Defaults
- `max_intervals_per_peer = 128`
- `threshold_suspect = 3.0`
- `threshold_dead = 8.0`
- `initial_interval_s = 1.0`

## Integration
- `fd` is used by `membership.PeerTable`.
- `record_heartbeat(...)` resets the peer to `alive` with `phi = 0.0`.
- Periodic evaluation recomputes `phi` and updates peer status when thresholds are crossed.
