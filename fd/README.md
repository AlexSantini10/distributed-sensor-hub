# Purpose

The `fd` module implements **heartbeat-based phi-accrual failure detection** for peer liveness assessment.

Its role in the overall system is to provide a detector-local suspicion signal (`phi`) and liveness classification (`alive`, `suspected`, `dead`) that is consumed by membership management (`membership.PeerTable`) to drive status transitions and subsequent gossip dissemination.

# File Overview

- `heartbeat.py`  
  Defines `HeartbeatMonitor` and immutable evaluation/observation records; maintains per-peer heartbeat history, computes phi through a pluggable estimator, and maps phi to detector-local failure classes.
- `phi_estimator.py`  
  Defines the estimator contract (`PhiEstimator`) and the default `ExponentialPhiEstimator` implementing `phi = -log10(P(T > t))` under an exponential inter-arrival model.
- `status.py`  
  Defines `FailureStatus`, the detector-local liveness enum (`ALIVE`, `SUSPECTED`, `DEAD`) intentionally decoupled from membership-domain status types.
- `__init__.py`  
  Exposes the module public surface (`HeartbeatMonitor`, estimators, status enum, result dataclasses) for integration by upper layers.

# Main Dependencies

- Internal: `fd.phi_estimator`  
  Supplies the statistical phi computation strategy used by `HeartbeatMonitor`.
- Internal: `fd.status`  
  Supplies detector-local status semantics returned by classification/evaluation operations.
- External: Python standard library (`time`, `threading`, `math`, `dataclasses`, `typing.Protocol`)  
  Provides monotonic timing, concurrency safety, numerical primitives, and typed structural contracts.

# High-Level Design

- **Core responsibilities**
  - Track per-peer last heartbeat arrival time.
  - Maintain a bounded sliding window of heartbeat inter-arrival intervals.
  - Compute `phi` from elapsed silence since last heartbeat.
  - Classify each peer into detector-local liveness classes using configurable thresholds.

- **Main data flow**
  - On heartbeat arrival, `record_heartbeat` updates arrival state, appends the new interval sample, and emits an observation with `phi = 0` and `alive` status.
  - During periodic checks, `evaluate_peer`/`evaluate_all` compute elapsed silence from monotonic time and invoke the configured phi estimator.
  - The estimator derives a survival probability and converts it to a suspicion score (`phi`), then classification maps that score to `alive` / `suspected` / `dead`.

- **Interactions with other modules**
  - `membership.PeerTable` is the primary consumer: it initializes/removes detector state, records direct heartbeat evidence, and applies periodic phi evaluations to membership status.
  - Runtime heartbeat loops and protocol heartbeat handlers interact with `fd` indirectly through `PeerTable`; `fd` remains transport-agnostic and does not depend on TCP or message codec internals.
  - Detector-local `FailureStatus` is translated by membership to replicated membership status, preserving separation between local failure suspicion and distributed membership state.