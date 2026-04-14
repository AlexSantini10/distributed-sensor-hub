# Module: fd

## Responsibility
Implements heartbeat-based phi-accrual failure detection to estimate peer liveness over time (`alive`, `suspected`, `dead`) without fixed timeout cutoffs.

## Key Concepts
- Phi-accrual detection: liveness is a continuously increasing suspicion score (`phi`) based on heartbeat silence.
- Sliding interval window: each peer keeps a bounded history of inter-arrival intervals used by the estimator.
- Pluggable estimator: statistical model is injected through the `PhiEstimator` protocol.

## Public API
### Class / Function: `HeartbeatMonitor`
- Purpose: track heartbeat arrivals per peer, compute `phi`, and classify peer status.
- Inputs: constructor thresholds/window settings; peer id and optional timestamps for initialize/record/evaluate methods.
- Outputs: `HeartbeatObservation` from `record_heartbeat`, `PhiEvaluation` from `evaluate_peer`/`evaluate_all`, snapshots from `get_intervals`.
- Side effects: mutates in-memory detector state (`_last_arrival_s`, `_intervals_s`) under lock.

### Class / Function: `HeartbeatObservation`
- Purpose: immutable result object describing one accepted heartbeat.
- Inputs: `peer_id`, `arrived_at_s`, optional `interval_s`, optional `sender_timestamp_ms`, `phi`, `status`.
- Outputs: dataclass instance consumed by upper layers.
- Side effects: none.

### Class / Function: `PhiEvaluation`
- Purpose: immutable result object describing one liveness evaluation.
- Inputs: `peer_id`, computed `phi`, derived `status`.
- Outputs: dataclass instance for one peer.
- Side effects: none.

### Class / Function: `PhiEstimator` (Protocol)
- Purpose: define the pluggable contract for `phi` computation.
- Inputs: `elapsed_s`, `intervals_s`, `initial_interval_s`.
- Outputs: numeric `phi` score (`float`).
- Side effects: none (pure computation expected).

### Class / Function: `ExponentialPhiEstimator`
- Purpose: default `PhiEstimator` implementation using exponential survival.
- Inputs: same contract as `PhiEstimator.compute_phi`.
- Outputs: `phi = -log10(P(T > t))` with numeric floor protection.
- Side effects: none.

## Data Structures
- `_last_arrival_s: dict[str, float]`: last heartbeat arrival timestamp per peer.
- `_intervals_s: dict[str, list[float]]`: bounded list of inter-arrival samples per peer.
- `HeartbeatObservation`: immutable heartbeat event snapshot.
- `PhiEvaluation`: immutable evaluation snapshot.

## Protocol / Messages (if applicable)
- Not applicable in this module: no wire message schema is defined here.
- Integration note: callers pass optional `sender_timestamp_ms` from heartbeat protocol messages to `record_heartbeat`.

## Concurrency Model
- Threads / locks used: one `threading.Lock` (`_lock`) in `HeartbeatMonitor`.
- Critical sections: all reads/writes of `_last_arrival_s` and `_intervals_s`, including interval-window trimming and `phi` computation inputs.

## Failure Handling
- Constructor validates configuration and raises `ValueError` for invalid thresholds/window/interval values.
- Unknown peer during evaluation returns `phi = 0.0` and classifies as `alive` (no exception).
- Negative/clock-skew timing effects are clamped to `0.0` elapsed/interval.
- Very large silence avoids math underflow using bounded survival floor (`1e-16`).

## Configuration
- `max_intervals_per_peer` (default `128`)
- `threshold_suspect` (default `3.0`)
- `threshold_dead` (default `8.0`, must be `>= threshold_suspect`)
- `initial_interval_s` (default `1.0`, must be `> 0`)
- Runtime env inputs (loaded outside this module): `PHI_THRESHOLD_SUSPECT`, `PHI_THRESHOLD_DEAD`, `PHI_INITIAL_INTERVAL_S`

## Dependencies
- Internal modules: `membership.status.NodeStatus`
- External libs: Python stdlib (`dataclasses`, `threading`, `time`, `math`, `typing`)

## Notes
- `record_heartbeat` always returns `status=alive` and `phi=0.0` at receipt time; suspicion is computed only in later evaluations.
- The default estimator anchors observed mean interval to `initial_interval_s` to reduce aggressiveness after short transient bursts.
- Public exports are centralized in `fd/__init__.py` (`HeartbeatMonitor`, `HeartbeatObservation`, `PhiEvaluation`, `PhiEstimator`, `ExponentialPhiEstimator`).
