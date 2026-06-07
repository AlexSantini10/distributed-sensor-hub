"""Provide framed TCP transport primitives for cluster communication.

Responsibilities:
    - Expose inbound and outbound transport components for node-to-node traffic.
    - Carry protocol messages as length-prefixed frames over TCP connections.
    - Isolate transport availability and framing contracts from message semantics.
"""
