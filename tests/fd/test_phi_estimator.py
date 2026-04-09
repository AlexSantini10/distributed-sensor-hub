"""Validate phi-estimator behavior under bursty heartbeat timings."""

from fd.phi_estimator import ExponentialPhiEstimator


def test_exponential_phi_is_anchored_to_initial_interval_floor() -> None:
    """Assert tiny observed intervals do not make one delay look immediately dead."""
    estimator = ExponentialPhiEstimator()

    phi = estimator.compute_phi(
        elapsed_s=2.2,
        intervals_s=(0.01, 0.02, 0.015, 0.01),
        initial_interval_s=1.0,
    )

    assert phi < 3.0


def test_exponential_phi_can_still_adapt_to_slower_observed_intervals() -> None:
    """Assert observed means above baseline are still used for phi computation."""
    estimator = ExponentialPhiEstimator()

    phi = estimator.compute_phi(
        elapsed_s=3.0,
        intervals_s=(3.0, 3.0, 3.0),
        initial_interval_s=1.0,
    )

    assert 0.43 < phi < 0.44
