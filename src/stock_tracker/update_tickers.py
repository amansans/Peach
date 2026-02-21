from stock_tracker.utils.logging_config import setup_logging
from stock_tracker.tickers.service import update_ticker_list
from stock_tracker.config.settings import settings


def main():
    setup_logging()  # Configure logging ONCE
    update_ticker_list(settings.TICKER_FILE)


if __name__ == "__main__":
    main()
