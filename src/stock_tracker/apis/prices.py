from fastapi import APIRouter, HTTPException
from stock_tracker.prices.storage_factory import get_price_factory
from stock_tracker.prices.fetch import fetch_stock_data
from stock_tracker.prices.service import update_single_ticker
from stock_tracker.prices.storage import FilePriceStorage

router = APIRouter()


@router.get("/{ticker}")
def get_prices(ticker: str):
    storage = get_price_factory()
    df = storage.load_price_parquet_file(ticker)
    return df.to_dict(orient="records")


@router.post("/{ticker}/update")
def update_ticker(ticker: str):
    try:
        storage = get_price_factory()
        update_single_ticker(ticker, storage)
        return {"status": "ok", "message": f"{ticker} updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
