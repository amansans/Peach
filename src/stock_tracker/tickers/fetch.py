from typing import Dict, List, Callable
from stock_tracker.config import settings
import logging
import pandas as pd
import requests


def fetch_index_tickers(
    urls: Dict[str, str] = settings.INDEX_URLS,
    headers: Dict[str, str] = settings.HEADERS,
    http_get: Callable = requests.get,
) -> List[str]:
    """Fetch tickers from configured index Wikipedia pages."""
    tickers: List[str] = []

    for index_name, url in urls.items():
        logging.info("Fetching tickers for %s", index_name)

        response = http_get(url, headers=headers, timeout=15)
        response.raise_for_status()

        tables = pd.read_html(response.text)

        if index_name == "S&P 500":
            symbols = tables[0]["Symbol"]

        # Some issue with the extract here. Perhaps HTML got updated
        # elif index_name == "Dow Jones":
        #     symbols = tables[2]["Symbol"]

        elif index_name == "Nasdaq 100":
            symbols = tables[4]["Ticker"]

        else:
            continue

        tickers.extend(symbols.tolist())

    return sorted(set(tickers))
