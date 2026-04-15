"""Define liveness classifications local to the failure detector."""

from __future__ import annotations

from enum import StrEnum


class FailureStatus(StrEnum):
    """Represent the detector-local liveness classification."""

    ALIVE = "alive"
    SUSPECTED = "suspected"
    DEAD = "dead"
