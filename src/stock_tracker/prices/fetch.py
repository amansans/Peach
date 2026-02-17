from stock_tracker.utils.date_util import today_str
import yfinance as yf
import pandas as pd
import logging


def fetch_stock_data(
    ticker: str,
    start_date: str = "1900-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Fetch historical data from Yahoo Finance.
    """
    end_date = end_date or today_str()

    logging.info("Fetching %s from %s to %s", ticker, start_date, end_date)

    df = yf.Ticker(ticker).history(start=start_date, end=end_date)

    if df.empty:
        logging.warning("No data returned for %s", ticker)

    return df
