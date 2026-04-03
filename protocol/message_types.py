"""Enumerate the protocol message categories exchanged between nodes.

Responsibilities:
    - Define the stable wire identifiers used in JSON message envelopes.
    - Group message types for membership, liveness, replication, synchronization,
      and error signaling.
"""

from enum import Enum


class MessageType(Enum):
	"""List the protocol message types supported by the transport layer."""

	JOIN_REQUEST = "JOIN_REQUEST"
	PEER_LIST = "PEER_LIST"

	PING = "PING"
	PONG = "PONG"

	SENSOR_UPDATE = "SENSOR_UPDATE"
	GOSSIP_STATE = "GOSSIP_STATE"

	FULL_SYNC_REQUEST = "FULL_SYNC_REQUEST"
	FULL_SYNC_RESPONSE = "FULL_SYNC_RESPONSE"

	ERROR = "ERROR"
	ACK = "ACK"
