from stock_tracker.tickers.storage import load_existing_tickers
from unittest.mock import patch
import pandas as pd
import pytest


@pytest.fixture
def mock_tickers():
    return pd.DataFrame({"Symbol": ["AAPL", "GOOG"]})


@pytest.fixture
def returnHTTPException():
    return Exception("DB Exploded")


def test_get_tickers(client, mock_tickers):
    with patch("stock_tracker.apis.ticker.load_existing_tickers") as mock_ticker_list:
        mock_ticker_list.return_value = mock_tickers

        r = client.get("/tickers")

        assert r.status_code == 200
        assert r.json() == {"tickers": ["AAPL", "GOOG"]}


def test_update_tickers(client):
    with patch("stock_tracker.apis.ticker.update_ticker_list") as mock_update:
        r = client.post("/tickers/update")

        assert r.status_code == 200
        assert r.json() == {"status": "ok", "message": "tickers updated"}
        mock_update.assert_called_once()


def test_update_tickers_with_exception(client, returnHTTPException):
    with patch("stock_tracker.apis.ticker.update_ticker_list") as mock_update:

        mock_update.side_effect = returnHTTPException
        r = client.post("/tickers/update")

        assert r.status_code == 500
        assert r.json() == {"detail": "DB Exploded"}
        mock_update.assert_called_once()
