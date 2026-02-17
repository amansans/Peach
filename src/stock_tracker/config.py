from pathlib import Path

# Base project root
BASE_DIR = Path(__file__).resolve().parents[2]
print(BASE_DIR)

# Data folder
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Price folder
PRICE_DIR = DATA_DIR / "prices"
PRICE_DIR.mkdir(exist_ok=True)

# Ticker file path
TICKER_FILE = DATA_DIR / "tickers.xlsx"

# External sources
INDEX_URLS = {
    "S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "Dow Jones": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
    "Nasdaq 100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}

# Browser headers
HEADERS = {"User-Agent": "Mozilla/5.0"}
