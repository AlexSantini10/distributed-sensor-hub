"""Define pluggable phi estimators used by heartbeat monitoring."""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class PhiEstimator(Protocol):
    """Define the statistical model contract used to compute phi."""

    def compute_phi(
        self,
        *,
        elapsed_s: float,
        intervals_s: tuple[float, ...],
        initial_interval_s: float,
    ) -> float:
        """Return the phi score for one peer at the current elapsed time."""
        ...


class ExponentialPhiEstimator:
    """Compute phi using an exponential survival model."""

    def compute_phi(
        self,
        *,
        elapsed_s: float,
        intervals_s: tuple[float, ...],
        initial_interval_s: float,
    ) -> float:
        """Return ``-log10(P(T > t))`` under an exponential inter-arrival model."""
        elapsed = max(0.0, elapsed_s)
        if intervals_s:
            mean_interval_s = max(0.001, sum(intervals_s) / len(intervals_s))
        else:
            mean_interval_s = max(0.001, initial_interval_s)

        lambda_rate = 1.0 / mean_interval_s
        survival = math.exp(-lambda_rate * elapsed)
        bounded_survival = max(survival, 1e-16)
        return -math.log10(bounded_survival)

