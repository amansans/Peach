from unittest.mock import patch
import pandas as pd


def test_get_prices(client):
    fake_df = pd.DataFrame({"Close": [100, 101]})

    with patch(
        "stock_tracker.apis.prices.FilePriceStorage.load_price_parquet_file"
    ) as mock_load:
        mock_load.return_value = fake_df

        r = client.get("/prices/AAPL")

        assert r.status_code == 200
        assert r.json() == fake_df.to_dict(orient="records")


def test_update_prices(client):
    with patch("stock_tracker.apis.prices.update_single_ticker") as mock_update:
        r = client.post("/prices/AAPL/update")

        assert r.status_code == 200
        mock_update.assert_called_once_with("AAPL")
