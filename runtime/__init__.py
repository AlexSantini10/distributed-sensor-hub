"""Provide runtime assembly for launching a sensor-hub node process.

Responsibilities:
    - Compose process bootstrap, networking, membership, and sensor subsystems.
    - Expose application-level startup and shutdown coordination for a node.
    - Keep runtime wiring separate from protocol and transport implementations.
"""
