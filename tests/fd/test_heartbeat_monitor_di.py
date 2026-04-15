"""Validate dependency inversion points in the heartbeat monitor."""

from __future__ import annotations

from fd.heartbeat import HeartbeatMonitor
from fd.status import FailureStatus


class ConstantPhiEstimator:
    """Return a fixed phi value to verify monitor-level inversion wiring."""

    def __init__(self, phi: float) -> None:
        self._phi = phi

    def compute_phi(
        self,
        *,
        elapsed_s: float,
        intervals_s: tuple[float, ...],
        initial_interval_s: float,
    ) -> float:
        return self._phi


def test_heartbeat_monitor_uses_injected_phi_estimator() -> None:
    """Assert HeartbeatMonitor classification depends on injected estimator output."""
    monitor = HeartbeatMonitor(
        threshold_suspect=3.0,
        threshold_dead=8.0,
        phi_estimator=ConstantPhiEstimator(phi=9.5),
    )
    monitor.initialize_peer("node-b", observed_at_s=100.0)

    evaluation = monitor.evaluate_peer("node-b", observed_at_s=101.0)

    assert evaluation.phi == 9.5
    assert evaluation.status is FailureStatus.DEAD

