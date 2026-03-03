from stock_tracker.config import settings
from pathlib import Path
import logging
import pandas as pd


class FilePriceStorage:
    def __init__(self, price_dir: Path | None = None):
        self.price_dir = price_dir or settings.PRICE_DIR

    def store_updated_prices(self, df: pd.DataFrame, ticker: str) -> None:
        """
        Store updated price movement for all tickers
        """
        file_path = self.price_dir / f"{ticker}.parquet"
        df.to_parquet(file_path)
        logging.info("%s successfully updated.", ticker)

    def load_price_parquet_file(self, ticker: str) -> pd.DataFrame:
        """
        return existing parquet file for a ticker if exists
        return empty dataframe if does not exist
        """
        file_path = self.price_dir / f"{ticker}.parquet"
        if file_path.exists():
            existing_df = pd.read_parquet(file_path)
        else:
            existing_df = pd.DataFrame([])
        return existing_df
