from stock_tracker.tickers.fetch import fetch_index_tickers


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


HTML_MAP = {
    "url1": """
        <table>
            <tr><th>Symbol</th></tr>
            <tr><td>AAPL</td></tr>
            <tr><td>MSFT</td></tr>
        </table>
    """,
    "url2": """
        <table><tr><th>X</th></tr></table>
        <table><tr><th>X</th></tr></table>
        <table>
            <tr><th>Symbol</th></tr>
            <tr><td>GOOG</td></tr>
        </table>
    """,
    "url3": """
        <table><tr><th>X</th></tr></table>
        <table><tr><th>X</th></tr></table>
        <table><tr><th>X</th></tr></table>
        <table><tr><th>X</th></tr></table>
        <table>
            <tr><th>Ticker</th></tr>
            <tr><td>AAPL</td></tr>
        </table>
    """,
}

URLS = {
    "S&P 500": "url1",
    "Dow Jones": "url2",
    "Nasdaq 100": "url3",
}


def fake_http_get(url, headers=None, timeout=15):
    return FakeResponse(HTML_MAP[url])


def test_fetch_index_tickers_parses_all_indexes_correctly():

    tickers = fetch_index_tickers(urls=URLS, headers=None, http_get=fake_http_get)
    assert tickers == ["AAPL", "GOOG", "MSFT"]
