from dotenv import load_dotenv
load_dotenv()

from utils.config import load_config
from utils.logging import setup_logging, get_logger


def main():
    config = load_config()
    setup_logging(config.node_id, config.log_level, config.log_file)

    log = get_logger(__name__, config.node_id)
    log.info("Node starting")
    log.info("Config loaded: host=%s port=%d", config.host, config.port)


if __name__ == "__main__":
    main()
