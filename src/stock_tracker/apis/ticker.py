from fastapi import APIRouter, HTTPException
from stock_tracker.tickers.storage_factory import get_ticker_storage
from stock_tracker.tickers.service import update_ticker_list
from stock_tracker.tickers.fetch import fetch_index_tickers

router = APIRouter()


@router.get("/")
def get_tickers():
    storage = get_ticker_storage()
    df = storage.load_existing_tickers()
    return {"tickers": df["Symbol"].tolist()}


@router.post("/update")
def update_tickers():
    try:
        storage = get_ticker_storage()
        print(storage)
        update_ticker_list(fetch_index_tickers, storage)
        return {"status": "ok", "message": "tickers updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
