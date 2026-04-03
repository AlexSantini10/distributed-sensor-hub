"""Provide membership primitives for peer discovery and view maintenance.

Responsibilities:
    - Define the peer record exchanged by membership and gossip flows.
    - Maintain the local peer table with thread-safe additive updates.
    - Expose handlers for join requests and peer-list convergence messages.
"""
