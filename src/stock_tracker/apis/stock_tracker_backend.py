from fastapi import FastAPI
from stock_tracker.apis.health import router as health_router
from stock_tracker.apis.ticker import router as tickers_router
from stock_tracker.apis.prices import router as prices_router
from stock_tracker.config.settings import settings


app = FastAPI(title=settings.APP_NAME)

app.include_router(health_router)
app.include_router(tickers_router, prefix="/tickers")
app.include_router(prices_router, prefix="/prices")
