from stock_tracker.prices.storage import store_updated_prices, load_price_parquet_file
from unittest.mock import patch
from stock_tracker.config.settings import settings
import pandas as pd
import pytest


@pytest.fixture
def valid_stock_data():
    """
    Fake stock data that yfinance would normally return.
    Use this to test the code without calling the real API.
    """
    return pd.DataFrame(
        {
            "Open": [150.0, 152.0, 151.0],
            "High": [151.0, 153.0, 152.0],
            "Low": [153.0, 154.0, 153.0],
            "Close": [149.0, 151.0, 150.0],
            "Volume": [1000000, 1100000, 1050000],
            "Dividends": [4, 5, 6],
            "Stock Splits": [2, 5, 7],
        }
    )


def test_saving_parquet_files_for_a_ticker(tmp_path, monkeypatch, valid_stock_data):
    """
    Test parquet files are being stored
    """

    mock_ticker = "TEST"
    monkeypatch.setattr(settings, "PRICE_DIR", tmp_path)

    store_updated_prices(valid_stock_data, mock_ticker)
    loaded_df = load_price_parquet_file(mock_ticker)

    assert valid_stock_data.equals(loaded_df)
