from pathlib import Path
from typing import List, Callable
import logging
import pandas as pd

from stock_tracker.tickers.fetch import fetch_index_tickers
from stock_tracker.tickers.storage import (
    load_existing_tickers,
    save_tickers,
)


def compute_updated_symbols(
    existing_symbols: set[str],
    latest_symbols: set[str],
) -> set[str] | None:
    """Return updated symbol set if changes exist."""
    if not existing_symbols:
        return latest_symbols

    new_symbols = latest_symbols - existing_symbols

    if not new_symbols:
        return None

    return new_symbols


def update_ticker_list(
    ticker_file: Path,
    fetch_func: Callable[[], List[str]] = fetch_index_tickers,
) -> None:
    """Compare new index tickers with stored tickers and update file."""
    existing_df = load_existing_tickers(ticker_file)
    existing_symbols = set(existing_df["Symbol"])
    latest_symbols = set(fetch_func())

    updated_symbols = compute_updated_symbols(
        existing_symbols,
        latest_symbols,
    )

    if updated_symbols is None:
        logging.info("No new tickers found.")
        return
    if len(existing_symbols) > 0:
        updated_tickers = list(existing_symbols) + (list(updated_symbols))
        logging.info("Saving updated ticker list.")
    else:
        updated_tickers = list(updated_symbols)

    updated_df = pd.DataFrame({"Symbol": sorted(updated_tickers)})
    save_tickers(updated_df, ticker_file)
