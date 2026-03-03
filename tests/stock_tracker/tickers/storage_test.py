from stock_tracker.tickers.storage import FileTickerStorage
from stock_tracker.config.settings import settings
import pandas as pd


def test_load_existing_tickers_when_file_does_not_exist(tmp_path, monkeypatch):
    fake_file = tmp_path / "tickers.xlsx"

    monkeypatch.setattr("stock_tracker.config.settings.TICKER_FILE", fake_file)
    storage = FileTickerStorage(fake_file)
    df = storage.load_existing_tickers()

    assert fake_file.exists()
    assert df.empty
    assert list(df.columns) == ["Symbol"]


def test_save_tickers_when_tickers_are_added(tmp_path):
    fake_file = tmp_path / "tickers.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "FB"]})

    storage = FileTickerStorage(fake_file)
    storage.save_tickers(df)
    saved_df = storage.load_existing_tickers()

    assert list(saved_df["Symbol"]) == ["AAPL", "FB"]
