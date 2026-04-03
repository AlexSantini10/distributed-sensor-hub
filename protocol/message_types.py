"""Define the stable protocol message categories exchanged between nodes.

Responsibilities:
    - Enumerate the wire identifiers used in JSON protocol envelopes.
    - Group message types for membership, liveness, replication, and control flows.
    - Preserve message-kind compatibility across transport and dispatcher layers.
"""

from enum import Enum


class MessageType(Enum):
	"""Enumerate the protocol message kinds supported by the node.

	Attributes:
		JOIN_REQUEST (str): Membership announcement used to advertise a node endpoint.
		PEER_LIST (str): Membership gossip payload containing known peer endpoints.
		PING (str): Liveness probe used for reachability checking.
		PONG (str): Liveness acknowledgement paired with ``PING``.
		SENSOR_UPDATE (str): Replicated sensor-state update subject to merge policy.
		GOSSIP_STATE (str): State-gossip message used for cluster convergence.
		FULL_SYNC_REQUEST (str): Request for a complete state transfer.
		FULL_SYNC_RESPONSE (str): Response carrying a complete state transfer.
		ERROR (str): Protocol-level error notification.
		ACK (str): Generic acknowledgement message.
	"""

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
