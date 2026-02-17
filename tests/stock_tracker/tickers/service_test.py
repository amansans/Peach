from stock_tracker.tickers.service import compute_updated_symbols, update_ticker_list
from stock_tracker.tickers.storage import load_existing_tickers, save_tickers

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
    save_tickers(df, fake_file)

    update_ticker_list(fake_file, mock_fetch_index_tickers)
    updated_df = load_existing_tickers(fake_file)

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG"]


def test_update_ticker_list_one_new_ticker(tmp_path):

    # build an existing_df
    fake_file = tmp_path / "ticker.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "GOOG", "FB"]})
    save_tickers(df, fake_file)

    update_ticker_list(fake_file, mock_fetch_index_tickers)
    updated_df = load_existing_tickers(fake_file)

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG", "FB"]


def test_update_ticker_list_multiple_new_tickers(tmp_path):

    # build an existing_df
    fake_file = tmp_path / "ticker.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "GOOG", "FB", "NIO", "TSLA"]})
    save_tickers(df, fake_file)

    update_ticker_list(fake_file, mock_fetch_index_tickers)
    updated_df = load_existing_tickers(fake_file)

    assert list(updated_df["Symbol"]) == ["AAPL", "GOOG", "FB", "NIO", "TSLA"]


def failing_fetch():
    raise RuntimeError("API is down")


def test_update_ticker_list_fetch_failure(tmp_path):
    fake_file = tmp_path / "ticker.xlsx"

    try:
        update_ticker_list(fake_file, failing_fetch)
        assert False, "Expected failure"
    except RuntimeError:
        pass
