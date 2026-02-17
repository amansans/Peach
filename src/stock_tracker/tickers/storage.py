from stock_tracker.utils.file_util import create_ticker_file
from pathlib import Path
import logging
import pandas as pd


def load_existing_tickers(ticker_file: Path) -> pd.DataFrame:
    """Load existing ticker list from Excel (if it exists)."""
    if not ticker_file.exists():
        logging.info("Ticker file does not exist yet.")
        create_ticker_file(ticker_file)
        logging.info("Ticker excel file created.")
        return pd.DataFrame(columns=["Symbol"])

    return pd.read_excel(ticker_file)


def save_tickers(df: pd.DataFrame, ticker_file: Path) -> None:
    """Persist ticker DataFrame to Excel."""
    df.to_excel(ticker_file, index=False)
    logging.info("Ticker list saved to %s", ticker_file.name)
