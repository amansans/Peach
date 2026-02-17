from stock_tracker.prices.service import (
    update_all_tickers,
    update_single_ticker,
    calculate_start_date_for_new_extract,
)
import pandas as pd
from unittest.mock import patch
from datetime import datetime
import pytest


@pytest.fixture
def existing_stock_data_with_existing_values():
    """
    Return an mock dataframe emulating actual data previously extracted from yfinance API
    """

    dates = [
        datetime(2026, 1, 26),
        datetime(2026, 1, 27),
        datetime(2026, 1, 28),
        datetime(2026, 1, 29),
    ]

    # Create DataFrame
    df = pd.DataFrame(
        {
            "Open": [251.244900, 258.927717, 257.409147, 257.758807],
            "High": [256.320153, 261.705117, 258.618008, 259.407258],
            "Low": [249.566478, 257.968592, 254.272083, 254.172166],
            "Close": [255.171234, 258.028534, 256.200287, 258.038544],
            "Volume": [55969200, 49648300, 41288000, 67253000],
            "Dividends": [0.00, 0.00, 0.00, 0.00],
            "Stock Splits": [0.0, 0.0, 0.0, 0.0],
        },
        index=dates,
    )

    df.index.name = "Date"
    return df


@pytest.fixture
def new_stock_data_extract_from_yfiance():
    """
    Return an mock dataframe emulating actual data previously extracted from yfinance API
    """

    dates = [
        datetime(2026, 1, 30),
        datetime(2026, 1, 31),
        datetime(2026, 2, 1),
        datetime(2026, 2, 2),
    ]

    # Create DataFrame
    df = pd.DataFrame(
        {
            "Open": [251.244900, 258.927717, 257.409147, 257.758807],
            "High": [256.320153, 261.705117, 258.618008, 259.407258],
            "Low": [249.566478, 257.968592, 254.272083, 254.172166],
            "Close": [255.171234, 258.028534, 256.200287, 258.038544],
            "Volume": [55969200, 49648300, 41288000, 67253000],
            "Dividends": [0.00, 0.00, 0.00, 0.00],
            "Stock Splits": [0.0, 0.0, 0.0, 0.0],
        },
        index=dates,
    )

    df.index.name = "Date"
    return df


@pytest.fixture
def existing_stock_data_with_no_values():
    """
    Return mock empty dataframe
    """
    return pd.DataFrame([])


@pytest.fixture
def concat_existing_and_new_dataframes(
    existing_stock_data_with_existing_values,
    new_stock_data_extract_from_yfiance,
):
    """
    merges existing and new dataframes and returns it concat
    """

    return pd.concat(
        [existing_stock_data_with_existing_values, new_stock_data_extract_from_yfiance]
    )


def test_calculate_start_date_for_new_extract_to_check_it_returns_last_day_plus_one(
    existing_stock_data_with_existing_values,
):
    """
    Test if last_date + 1 date is retruned as a string
    """
    latest_date_str = calculate_start_date_for_new_extract(
        existing_stock_data_with_existing_values
    )
    assert latest_date_str == "2026-01-30"


def test_calculate_start_date_for_new_extract_to_check_it_returns_last_day_plus_one_as_str(
    existing_stock_data_with_existing_values,
):
    """
    Test if last_date + 1 date is retruned as a string
    """
    latest_date_str = calculate_start_date_for_new_extract(
        existing_stock_data_with_existing_values
    )
    assert type(latest_date_str) is str


def test_add_data_to_ticker_with_no_existing_values(
    existing_stock_data_with_no_values,
    new_stock_data_extract_from_yfiance,
):
    """
    Test if data is being added correctly to a ticker with no values
    """
    with patch(
        "stock_tracker.prices.service.load_price_parquet_file"
    ) as mock_load, patch(
        "stock_tracker.prices.service.fetch_stock_data"
    ) as mock_fetch, patch(
        "stock_tracker.prices.service.store_updated_prices"
    ) as mock_store:

        mock_load.return_value = existing_stock_data_with_no_values
        mock_fetch.return_value = new_stock_data_extract_from_yfiance

        update_single_ticker("TEST")

        mock_load.assert_called_once_with("TEST")

        mock_fetch.assert_called_once_with("TEST")

        mock_store.assert_called_once()

        stored_df = mock_store.call_args[0][0]

        assert stored_df.equals(new_stock_data_extract_from_yfiance)


def test_add_data_to_ticker_with_existing_values(
    existing_stock_data_with_existing_values,
    new_stock_data_extract_from_yfiance,
    concat_existing_and_new_dataframes,
):
    """
    Test if data is being added correctly to a ticker with existing values
    """
    with patch(
        "stock_tracker.prices.service.load_price_parquet_file"
    ) as mock_load, patch(
        "stock_tracker.prices.service.fetch_stock_data"
    ) as mock_fetch, patch(
        "stock_tracker.prices.service.store_updated_prices"
    ) as mock_store, patch(
        "stock_tracker.prices.service.today_str",
        return_value="2026-02-16",
    ):

        mock_load.return_value = existing_stock_data_with_existing_values
        mock_fetch.return_value = new_stock_data_extract_from_yfiance

        update_single_ticker("TEST")

        mock_load.assert_called_once_with("TEST")
        mock_fetch.assert_called_once_with("TEST", start_date="2026-01-30")
        mock_store.assert_called_once()

        stored_df = mock_store.call_args[0][0]
        ticker_arg = mock_store.call_args[0][1]

        assert stored_df.equals(concat_existing_and_new_dataframes)
        assert ticker_arg == "TEST"
        assert len(stored_df) == 8
        assert stored_df.index.is_monotonic_increasing
        assert not stored_df.index.duplicated().any()
