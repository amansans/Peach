from stock_tracker.tickers.storage import load_existing_tickers, save_tickers
from stock_tracker import config
import pandas as pd


def test_load_existing_tickers_when_file_does_not_exist(tmp_path, monkeypatch):
    fake_file = tmp_path / "tickers.xlsx"
    monkeypatch.setattr(config, "TICKER_FILE", fake_file)

    df = load_existing_tickers(fake_file)

    assert fake_file.exists()
    assert df.empty
    assert list(df.columns) == ["Symbol"]


def test_save_tickers_when_tickers_are_added(tmp_path):
    fake_file = tmp_path / "tickers.xlsx"
    df = pd.DataFrame({"Symbol": ["AAPL", "FB"]})

    save_tickers(df, fake_file)
    saved_df = load_existing_tickers(fake_file)

    assert list(saved_df["Symbol"]) == ["AAPL", "FB"]
