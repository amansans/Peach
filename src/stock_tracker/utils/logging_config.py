import logging


def setup_logging(level=logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")
