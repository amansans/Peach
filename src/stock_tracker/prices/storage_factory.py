from stock_tracker.prices.storage import FilePriceStorage
from stock_tracker.prices.storage import PriceStorage


def get_price_factory() -> PriceStorage:
    return FilePriceStorage()
