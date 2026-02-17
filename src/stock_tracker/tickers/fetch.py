from typing import Dict, List, Callable
import logging
import pandas as pd
import requests

from stock_tracker.config import INDEX_URLS, HEADERS


def fetch_index_tickers(
    urls: Dict[str, str] = INDEX_URLS,
    headers: Dict[str, str] = HEADERS,
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

        elif index_name == "Dow Jones":
            symbols = tables[2]["Symbol"]

        elif index_name == "Nasdaq 100":
            symbols = tables[4]["Ticker"]

        else:
            continue

        tickers.extend(symbols.tolist())

    return sorted(set(tickers))
