"""Pluggable phi estimators used by heartbeat-based failure detection.

This module exposes:
- ``PhiEstimator``: structural contract for phi models;
- ``ExponentialPhiEstimator``: default implementation based on an
  exponential inter-arrival assumption.
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class PhiEstimator(Protocol):
    """Structural contract for statistical phi models.

    Any class with a compatible ``compute_phi`` method is accepted by type
    checkers as a ``PhiEstimator`` (explicit inheritance is optional).
    """

    def compute_phi(
        self,
        *,
        elapsed_s: float,
        intervals_s: tuple[float, ...],
        initial_interval_s: float,
    ) -> float:
        """Return the phi score for one peer.

        Args:
            elapsed_s: Seconds elapsed since the last accepted heartbeat.
            intervals_s: Recent inter-arrival samples for the same peer.
            initial_interval_s: Baseline expected interval configured at startup.
        """
        ...


class ExponentialPhiEstimator:
    """Compute phi from an exponential survival model.

    Under the memoryless exponential assumption:
    ``phi = -log10(P(T > t)) = -log10(exp(-lambda * t))``.
    """

    def compute_phi(
        self,
        *,
        elapsed_s: float,
        intervals_s: tuple[float, ...],
        initial_interval_s: float,
    ) -> float:
        """Compute ``-log10(P(T > t))`` for the current elapsed time.

        The expected interval is clamped by ``initial_interval_s`` to avoid
        over-reacting when a few very short intervals temporarily appear.
        """
        elapsed = max(0.0, elapsed_s)
        # Anchor expectation to the configured baseline so transient bursts of
        # short intervals do not make the detector too aggressive.
        baseline_interval_s = max(0.001, initial_interval_s)
        if intervals_s:
            observed_mean_s = sum(intervals_s) / len(intervals_s)
            mean_interval_s = max(baseline_interval_s, observed_mean_s)
        else:
            mean_interval_s = baseline_interval_s

        # lambda = 1 / E[T] for an exponential variable with mean E[T].
        lambda_rate = 1.0 / mean_interval_s
        survival = math.exp(-lambda_rate * elapsed)
        # Numerical floor: prevent log10(0) when elapsed is very large.
        bounded_survival = max(survival, 1e-16)
        return -math.log10(bounded_survival)
