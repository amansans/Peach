from stock_tracker.config import settings
import logging
import pandas as pd


def store_updated_prices(df: pd.DataFrame, ticker: str) -> None:
    """
    Store updated price movement for all tickers
    """
    file_path = settings.PRICE_DIR / f"{ticker}.parquet"
    df.to_parquet(file_path)
    logging.info("%s successfully updated.", ticker)


def load_price_parquet_file(ticker: str) -> pd.DataFrame:
    """
    return existing parquet file for a ticker if exists
    return empty dataframe if does not exist
    """
    file_path = settings.PRICE_DIR / f"{ticker}.parquet"
    if file_path.exists():
        existing_df = pd.read_parquet(file_path)
    else:
        existing_df = pd.DataFrame([])
    return existing_df
