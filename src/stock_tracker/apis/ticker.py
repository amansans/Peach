from fastapi import APIRouter, HTTPException
from stock_tracker.tickers.service import update_ticker_list
from stock_tracker.tickers.storage import load_existing_tickers
from stock_tracker.config.settings import settings

router = APIRouter()


@router.get("/")
def get_tickers():
    df = load_existing_tickers(settings.TICKER_FILE)
    return {"tickers": df["Symbol"].tolist()}


@router.post("/update")
def update_tickers():
    try:
        update_ticker_list(settings.TICKER_FILE)
        return {"status": "ok", "message": "tickers updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
