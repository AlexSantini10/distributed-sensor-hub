from protocol.dispatcher import MessageDispatcher
from protocol.message_types import MessageType
from protocol import handlers


def setup_protocol() -> MessageDispatcher:
    dispatcher = MessageDispatcher()

    dispatcher.register(
        MessageType.JOIN_REQUEST, 
        handlers.handle_join_request
    )
    dispatcher.register(
        MessageType.PEER_LIST, 
        handlers.handle_peer_list
    )

    dispatcher.register(
        MessageType.PING, 
        handlers.handle_ping
    )
    dispatcher.register(
        MessageType.PONG, 
        handlers.handle_pong
    )

    dispatcher.register(
        MessageType.SENSOR_UPDATE, 
        handlers.handle_sensor_update
    )
    dispatcher.register(
        MessageType.GOSSIP_STATE, 
        handlers.handle_gossip_state
    )

    dispatcher.register(
        MessageType.FULL_SYNC_REQUEST,
        handlers.handle_full_sync_request,
    )
    dispatcher.register(
        MessageType.FULL_SYNC_RESPONSE,
        handlers.handle_full_sync_response,
    )

    dispatcher.register(
        MessageType.ERROR, 
        handlers.handle_error
    )
    dispatcher.register(
        MessageType.ACK, 
        handlers.handle_ack
    )

    return dispatcher
