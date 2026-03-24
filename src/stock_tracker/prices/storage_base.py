from typing import Protocol
import pandas as pd


class PriceStorage(Protocol):

    def store_updated_prices(self, df: pd.DataFrame, ticker: str) -> None: ...

    def load_price_parquet_file(self, ticker: str) -> pd.DataFrame: ...
