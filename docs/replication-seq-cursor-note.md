# Seq-Based Delta Cursor Refactor

## What Changed

- Replaced `GET_DELTA` cursor payload from `since_ts_ms` to `from_seq`.
- Added transport-level `seq` to replication delta entries and propagated it through `SENSOR_UPDATE` payloads when available.
- Updated state delta retrieval to select by sequence (`seq > from_seq`) and detect stale cursors by history bounds (`from_seq < oldest_seq - 1`).
- Kept LWW conflict resolution unchanged: winners are still decided by `(ts_ms, origin)`.
- Updated pull flow to request deltas using per-peer sequence cursor tracking instead of timestamp-derived watermarking.
- Added/updated unit tests for:
  - seq ordering in bounded buffers,
  - seq-based incremental reads,
  - stale cursor fallback (`DELTA_UNAVAILABLE`),
  - consecutive no-gap/no-duplicate cursor progression,
  - pull-sequence observation wiring.

## Why `seq` Is Safer Than `ts_ms` Here

- `seq` is monotonic per node and append-order deterministic in the delta buffer.
- It avoids ambiguity from timestamp collisions and clock skew.
- It prevents cursor instability caused by wall-clock discontinuities (restart timing, drift, NTP adjustments).
- It provides exact transport boundaries for incremental reads (`from_seq` -> `seq > from_seq`) without relying on time semantics.

## Remaining Limitations

- Delta history is still bounded and in-memory; old cursors still require fallback to full sync (`DELTA_UNAVAILABLE`).
- Sequence values are local to each node's replication stream and are not globally comparable across nodes.
- No durable replication log is introduced, so restart behavior remains bounded by current in-memory retention guarantees.
