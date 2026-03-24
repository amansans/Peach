from stock_tracker.prices.service import update_all_tickers
from stock_tracker.utils.logging_config import setup_logging
from stock_tracker.prices.storage import FilePriceStorage


def main():
    setup_logging()
    update_all_tickers(FilePriceStorage())


if __name__ == "__main__":
    main()
