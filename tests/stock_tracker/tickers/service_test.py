from stock_tracker.tickers.service import compute_updated_symbols, update_ticker_list
from stock_tracker.tickers.storage import FileTickerStorage

import pandas as pd


def test_compute_updated_symbols_with_no_existing_symbols():

    mock_existing_symbols = []
    mock_latest_symbols = ["AAPL", "GOOG"]

    symbols = compute_updated_symbols(mock_existing_symbols, mock_latest_symbols)

    assert list(symbols) == ["AAPL", "GOOG"]


def test_compute_updated_symbols_with_one_existing_symbols():

    mock_existing_symbols = set(["FB"])
    mock_latest_symbols = set(["AAPL", "GOOG", "FB"])

    symbols = compute_updated_symbols(mock_existing_symbols, mock_latest_symbols)

    assert set(symbols) == set(["AAPL", "GOOG"])


def test_compute_updated_symbols_no_new_symbols():

    mock_existing_symbols = set(["AAPL", "GOOG"])
    mock_latest_symbols = set(["AAPL", "GOOG"])

    symbols = compute_updated_symbols(mock_existing_symbols, mock_latest_symbols)

    assert symbols is None


# fetch_index_tickers returns sorted set of tickers


def mock_fetch_index_tickers():
    return ["AAPL", "GOOG"]


def test_update_ticker_list_with_no_new_data(tmp_path):

    # build an existing_df
    fake_file = tmp_path / "ticker.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "GOOG"]})
    storage = FileTickerStorage(fake_file)
    storage.save_tickers(df)

    update_ticker_list(mock_fetch_index_tickers, storage)
    updated_df = storage.load_existing_tickers()

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG"]


def test_update_ticker_list_one_new_ticker(tmp_path):

    # build an existing_df
    fake_file = tmp_path / "ticker.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "GOOG", "FB"]})
    storage = FileTickerStorage(fake_file)
    storage.save_tickers(df)

    update_ticker_list(mock_fetch_index_tickers, storage)
    updated_df = storage.load_existing_tickers()

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG", "FB"]


def test_update_ticker_list_multiple_new_tickers(tmp_path):

    # build an existing_df
    fake_file = tmp_path / "ticker.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "GOOG", "FB", "NIO", "TSLA"]})
    storage = FileTickerStorage(fake_file)
    storage.save_tickers(df)

    update_ticker_list(mock_fetch_index_tickers, storage)
    updated_df = storage.load_existing_tickers()

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG", "FB", "NIO", "TSLA"]
