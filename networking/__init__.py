"""Networking primitives for framed TCP transport between cluster nodes.

Responsibilities:
    - Expose client and server components for node-to-node communication.
    - Carry protocol messages as length-prefixed byte frames over TCP.
    - Isolate transport concerns from higher-level distributed-state semantics.

The package transports messages used by membership, gossip, and state
replication layers, but it does not interpret merge rules such as
last-writer-wins (LWW). Those semantics are delegated to protocol and state
management modules.
"""
