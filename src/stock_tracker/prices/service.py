from stock_tracker.config import settings
from stock_tracker.prices.fetch import fetch_stock_data
from stock_tracker.utils.date_util import today_str
from stock_tracker.prices.storage import FilePriceStorage
from datetime import timedelta
import logging
import pandas as pd


def load_tickers() -> pd.Series:
    """Load ticker symbols from Excel file."""
    df = pd.read_excel(settings.TICKER_FILE)
    return df["Symbol"].dropna().unique()


def calculate_start_date_for_new_extract(df: pd.DataFrame) -> str:
    """
    Calculate the start_date for ticker's yfinance data extract
    The start_date begins from the most recent date + 1 day if an extract is already present for the ticker
    The start date is the default data (1900-01-01) if previous extract is not present for the ticker or the extracted file is present but there is no data in it
    """

    last_date = df.index.max() + timedelta(days=1)
    last_date_str = last_date.strftime("%Y-%m-%d")
    return last_date_str


def update_single_ticker(ticker: str) -> None:
    """
    Update price data for a single ticker.
    """
    storage = FilePriceStorage()
    existing_df = storage.load_price_parquet_file(ticker)

    if not existing_df.empty:
        last_date_str = calculate_start_date_for_new_extract(existing_df)

        if last_date_str >= today_str():
            logging.info("%s already up to date.", ticker)
            return
        # Retruns data for the missing days
        new_data = fetch_stock_data(ticker, start_date=last_date_str)

        if new_data.empty:
            return

        # Add datapull to existing data
        new_df = pd.concat([existing_df, new_data])

    else:
        logging.info("%s does not exist. Fetching full history.", ticker)
        new_df = fetch_stock_data(ticker)

    # Clean and store
    new_df = new_df[~new_df.index.duplicated(keep="last")]
    new_df.sort_index(inplace=True)
    storage = FilePriceStorage()
    storage.store_updated_prices(new_df, ticker)


def update_all_tickers() -> None:
    """
    Update all tickers listed in the Excel file.
    """
    tickers = load_tickers()

    for ticker in tickers:
        try:
            update_single_ticker(ticker)
        except Exception as exc:
            logging.error("Error updating %s: %s", ticker, exc)
