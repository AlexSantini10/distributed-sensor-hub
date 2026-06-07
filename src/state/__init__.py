"""Expose replicated node-state components.

Responsibilities:
    - Group event normalization, LWW storage, and replication publishing modules.
    - Define the package boundary for state-management concerns.
"""

from state.contracts import RecordMergeStore, StateStoreLike
from state.policy import LwwMergePolicy, MergePolicy

__all__ = [
    "RecordMergeStore",
    "StateStoreLike",
    "LwwMergePolicy",
    "MergePolicy",
]
