from protocol.message import Message


def handle_join_request(msg: Message) -> None:
    raise NotImplementedError("JOIN_REQUEST not implemented yet")


def handle_peer_list(msg: Message) -> None:
    raise NotImplementedError("PEER_LIST not implemented yet")


def handle_ping(msg: Message) -> None:
    raise NotImplementedError("PING not implemented yet")


def handle_pong(msg: Message) -> None:
    raise NotImplementedError("PONG not implemented yet")


def handle_sensor_update(msg: Message) -> None:
    raise NotImplementedError("SENSOR_UPDATE not implemented yet")


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
