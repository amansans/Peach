from stock_tracker.prices.fetch import fetch_stock_data
from unittest.mock import patch
import yfinance as yf
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


@pytest.fixture
def empty_stock_data():
    """Empty DataFrame - what yfinance returns for invalid tickers."""
    return pd.DataFrame()


def test_default_start_date_is_1900(valid_stock_data: pd.DataFrame):
    """
    Test the default start date is set to 1900-01-01
    """
    with patch("stock_tracker.prices.fetch.yf.Ticker") as yf_mock:
        yf_mock.return_value.history.return_value = valid_stock_data

        fetch_stock_data("AAPL")

        call_args = yf_mock.return_value.history.call_args
        assert call_args.kwargs["start"] == "1900-01-01"


def test_default_end_date_is_todays_date(valid_stock_data: pd.DataFrame):
    """
    Test the default end date is set to todays date
    """
    with patch("stock_tracker.prices.fetch.yf.Ticker") as yf_mock, patch(
        "stock_tracker.prices.fetch.today_str"
    ) as today_str_mock:
        yf_mock.return_value.history.return_value = valid_stock_data
        today_str_mock.return_value = "2026-02-16"

        fetch_stock_data("AAPL", start_date="2024-01-01")
        call_args = yf_mock.return_value.history.call_args
        assert call_args.kwargs["end"] == "2026-02-16"


def test_default_start_date_is_defined(valid_stock_data: pd.DataFrame):
    """
    Test the default end date is set to todays date
    """
    with patch("stock_tracker.prices.fetch.yf.Ticker") as yf_mock:
        yf_mock.return_value.history.return_value = valid_stock_data

        fetch_stock_data("AAPL", start_date="2025-01-01")
        call_args = yf_mock.return_value.history.call_args
        assert call_args.kwargs["start"] == "2025-01-01"


def test_empty_df_response(empty_stock_data: pd.DataFrame):
    """
    Test the response when ticker is delisted or does not return data
    """
    with patch("stock_tracker.prices.fetch.yf.Ticker") as yf_mock:
        yf_mock.return_value.history.return_value = empty_stock_data

        df = fetch_stock_data("AAPL", start_date="2025-01-01")

        assert df.empty


def test_returns_dataframe_from_yfinance(valid_stock_data):
    """
    Test that function returns the DataFrame that yfinance gives
    """
    with patch("stock_tracker.prices.fetch.yf.Ticker") as yf_mock:
        yf_mock.return_value.history.return_value = valid_stock_data

        result = fetch_stock_data("AAPL")

        assert result.equals(valid_stock_data)


def test_columns_from_real_api(valid_stock_data):
    """
    Test the columns in api match the requirements
    """
    yf_dataframe = fetch_stock_data("AAPL", "2000-01-01", "2000-01-31")

    assert yf_dataframe.columns.equals(valid_stock_data.columns)
