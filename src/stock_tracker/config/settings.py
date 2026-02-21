from pathlib import Path
from pydantic_settings import BaseSettings

# Your existing base dir logic (keep this)
BASE_DIR = Path(__file__).resolve().parents[3]

# External sources
INDEX_URLS = {
    "S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "Dow Jones": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
    "Nasdaq 100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}

# Browser headers
HEADERS = {"User-Agent": "Mozilla/5.0"}


class Settings(BaseSettings):
    DATA_DIR: Path = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)

    PRICE_DIR: Path = BASE_DIR / "data" / "prices"
    PRICE_DIR.mkdir(exist_ok=True)

    TICKER_FILE: Path = BASE_DIR / "data" / "tickers.xlsx"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/stock_tracker"
    LOG_LEVEL: str = "INFO"

    APP_NAME: str = "Stock Tracker"

    class Config:
        env_file = ".env"


settings = Settings()

PRICE_DIR = settings.PRICE_DIR
TICKER_FILE = settings.TICKER_FILE
DATA_DIR = settings.DATA_DIR

print(BASE_DIR)
