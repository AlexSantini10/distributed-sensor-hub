# protocol/handlers.py
from protocol.message import Message
from utils.logging import get_logger


def handle_join_request(msg: Message) -> None:
	raise NotImplementedError("JOIN_REQUEST not implemented here (use membership handlers)")


def handle_peer_list(msg: Message) -> None:
	raise NotImplementedError("PEER_LIST not implemented here (use membership handlers)")


def handle_ping(msg: Message) -> None:
	log = get_logger(__name__, msg.sender_id)
	log.info(f"Received PING with payload={msg.payload}")
	raise NotImplementedError("PING not implemented yet")


def handle_pong(msg: Message) -> None:
	raise NotImplementedError("PONG not implemented yet")


def make_sensor_update_handler(state_worker, self_node_id: str):
	"""
	Create a SENSOR_UPDATE handler bound to the local NodeStateWorker.

	Payload contract:
	{
		"sensor_id": str,
		"value": any JSON,
		"ts_ms": int,
		"origin": str,            # optional, defaults to msg.sender_id
		"meta": { ... }           # optional
	}
	"""
	log = get_logger(__name__, self_node_id)

	def handle_sensor_update(msg: Message) -> None:
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
	log = get_logger(__name__, msg.sender_id)
	log.warning("SENSOR_UPDATE received but handler is not wired")
	return


def handle_gossip_state(msg: Message) -> None:
	raise NotImplementedError("GOSSIP_STATE not implemented yet")


def handle_full_sync_request(msg: Message) -> None:
	raise NotImplementedError("FULL_SYNC_REQUEST not implemented yet")


def handle_full_sync_response(msg: Message) -> None:
	raise NotImplementedError("FULL_SYNC_RESPONSE not implemented yet")


def handle_error(msg: Message) -> None:
	raise NotImplementedError("ERROR not implemented yet")


def handle_ack(msg: Message) -> None:
	raise NotImplementedError("ACK not implemented yet")