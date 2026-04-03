"""Provide default protocol handlers and handler factories.

Responsibilities:
    - Define placeholders for protocol message types owned by other subsystems.
    - Bind node-local dependencies into protocol handlers when wiring the node.
    - Enforce message payload contracts for replicated sensor updates.
"""

from protocol.message import Message
from utils.logging import get_logger


def handle_join_request(msg: Message) -> None:
	"""Reject direct handling of a membership join request in this module.

	Args:
		msg: Inbound ``JOIN_REQUEST`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because membership owns this message type.
	"""
	raise NotImplementedError("JOIN_REQUEST not implemented here (use membership handlers)")


def handle_peer_list(msg: Message) -> None:
	"""Reject direct handling of a membership peer list in this module.

	Args:
		msg: Inbound ``PEER_LIST`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because membership owns this message type.
	"""
	raise NotImplementedError("PEER_LIST not implemented here (use membership handlers)")


def handle_ping(msg: Message) -> None:
	"""Log receipt of a liveness probe and reject unsupported processing.

	Args:
		msg: Inbound ``PING`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because ping handling is not implemented yet.
	"""
	log = get_logger(__name__, msg.sender_id)
	log.info(f"Received PING with payload={msg.payload}")
	raise NotImplementedError("PING not implemented yet")


def handle_pong(msg: Message) -> None:
	"""Reject processing of an unimplemented liveness acknowledgement.

	Args:
		msg: Inbound ``PONG`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because pong handling is not implemented yet.
	"""
	raise NotImplementedError("PONG not implemented yet")


def make_sensor_update_handler(state_worker, self_node_id: str):
	"""Create a handler for replicated sensor updates.

	The returned handler expects a ``SENSOR_UPDATE`` payload with the fields
	``sensor_id``, ``value``, ``ts_ms``, optional ``origin``, and optional
	``meta``. Updates are merged through ``state_worker.merge_update`` using the
	message payload as the authoritative replication contract. Merge semantics are
	delegated to the state worker, which is expected to apply the project's
	last-writer-wins policy based on ``ts_ms`` and origin metadata.

	Args:
		state_worker: Local state merge component exposing ``merge_update``.
		self_node_id: Identifier of the local node used for logger scoping.

	Returns:
		callable[[Message], None]: Handler that validates and merges
		``SENSOR_UPDATE`` messages.
	"""
	log = get_logger(__name__, self_node_id)

	def handle_sensor_update(msg: Message) -> None:
		"""Merge a replicated sensor update into local state.

		Invalid payloads are logged and ignored so malformed gossip does not crash
		the receiving node. A successful merge means the incoming version won the
		state worker's conflict-resolution policy.

		Args:
			msg: Inbound ``SENSOR_UPDATE`` message.

		Returns:
			None.
		"""
		payload = msg.payload or {}

		sensor_id = payload.get("sensor_id")
		value = payload.get("value")
		ts_ms = payload.get("ts_ms")
		origin = payload.get("origin") or msg.sender_id
		meta = payload.get("meta") or {}

		if not isinstance(sensor_id, str) or sensor_id == "":
			log.warning("Invalid SENSOR_UPDATE: missing/invalid sensor_id")
			return

		if not isinstance(origin, str) or origin == "":
			log.warning("Invalid SENSOR_UPDATE: missing/invalid origin")
			return

		if not isinstance(ts_ms, int):
			log.warning("Invalid SENSOR_UPDATE: missing/invalid ts_ms")
			return

		try:
			applied = state_worker.merge_update(
				sensor_id=sensor_id,
				value=value,
				ts_ms=ts_ms,
				origin=origin,
				meta=meta,
			)
		except Exception:
			log.error("Failed to merge SENSOR_UPDATE", exc_info=True)
			return

		if applied:
			log.info(
				f"SENSOR_UPDATE applied: sensor={sensor_id} origin={origin} ts={ts_ms}"
			)

	return handle_sensor_update


def handle_sensor_update(msg: Message) -> None:
	"""Warn that sensor-update handling has not been wired for this node.

	Args:
		msg: Inbound ``SENSOR_UPDATE`` message.

	Returns:
		None.
	"""
	log = get_logger(__name__, msg.sender_id)
	log.warning("SENSOR_UPDATE received but handler is not wired")
	return


def handle_gossip_state(msg: Message) -> None:
	"""Reject processing of an unimplemented state gossip message.

	Args:
		msg: Inbound ``GOSSIP_STATE`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because gossip-state handling is not implemented yet.
	"""
	raise NotImplementedError("GOSSIP_STATE not implemented yet")


def handle_full_sync_request(msg: Message) -> None:
	"""Reject processing of an unimplemented full-sync request.

	Args:
		msg: Inbound ``FULL_SYNC_REQUEST`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because full-sync request handling is not implemented yet.
	"""
	raise NotImplementedError("FULL_SYNC_REQUEST not implemented yet")


def handle_full_sync_response(msg: Message) -> None:
	"""Reject processing of an unimplemented full-sync response.

	Args:
		msg: Inbound ``FULL_SYNC_RESPONSE`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because full-sync response handling is not implemented yet.
	"""
	raise NotImplementedError("FULL_SYNC_RESPONSE not implemented yet")


def handle_error(msg: Message) -> None:
	"""Reject processing of an unimplemented protocol error message.

	Args:
		msg: Inbound ``ERROR`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because error-message handling is not implemented yet.
	"""
	raise NotImplementedError("ERROR not implemented yet")


def handle_ack(msg: Message) -> None:
	"""Reject processing of an unimplemented acknowledgement message.

	Args:
		msg: Inbound ``ACK`` message.

	Returns:
		None.

	Raises:
		NotImplementedError: Always, because acknowledgement handling is not implemented yet.
	"""
	raise NotImplementedError("ACK not implemented yet")
