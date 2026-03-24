from stock_tracker.tickers.storage import FileTickerStorage
from stock_tracker.tickers.storage import TickerStorage


def get_ticker_storage() -> TickerStorage:
    return FileTickerStorage()
