import logging
from stock_tracker.config.settings import settings


def setup_logging(level=logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")
