import time
from utils.config import load_config
from utils.logging import setup_logging, get_logger
from protocol.setup import setup_protocol
from networking.tcp_server import TcpServer
from dotenv import load_dotenv
load_dotenv()



def main():
    config = load_config()
    setup_logging(config.node_id, config.log_level, config.log_file)
    log = get_logger(__name__, config.node_id)

    dispatcher = setup_protocol()
    server = TcpServer(config.host, config.port, dispatcher)

    log.info("Node starting")
    server.start()

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Node shutting down")
        server.stop()


if __name__ == "__main__":
    main()
