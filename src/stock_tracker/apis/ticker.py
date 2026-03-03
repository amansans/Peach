from fastapi import APIRouter, HTTPException
from stock_tracker.tickers.service import update_ticker_list
from stock_tracker.tickers.storage import FileTickerStorage
from stock_tracker.config.settings import settings

router = APIRouter()


@router.get("/")
def get_tickers():
    storage = FileTickerStorage()
    df = storage.load_existing_tickers()
    return {"tickers": df["Symbol"].tolist()}


@router.post("/update")
def update_tickers():
    try:
        update_ticker_list(settings.TICKER_FILE)
        return {"status": "ok", "message": "tickers updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
