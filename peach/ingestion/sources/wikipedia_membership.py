"""Wikipedia constituent-list scraper.

Scrapes the *current-as-of-today* constituents of the SP500, NDX, and DJI
from their respective Wikipedia article tables.  Historical revision
parsing (the proper survivorship-bias defense) is a separate one-shot
scraper that lives outside Phase 1.

URLs scraped::

    https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
    https://en.wikipedia.org/wiki/Nasdaq-100
    https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average

Fragility note
--------------
Wikipedia constituent tables share a fairly stable structure (always a
``<table class="wikitable">`` with the symbol in the first column), but
the exact column count and order shifts.  The parser is therefore
*positional only for the first column* — it locates the table by a
heuristic and reads the first ``<td>`` of each row as the ticker symbol.
Anything else is intentionally ignored.

If Wikipedia restructures and the parser starts emitting zero rows, the
data-quality job will flag the membership table as stale before
downstream code starts producing wrong answers.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import structlog
from bs4 import BeautifulSoup

from peach.db.base import utcnow
from peach.ingestion.base import DataSource, ParsedMembership
from peach.ingestion.http import fetch_text

log = structlog.get_logger(__name__)


# URL per index_code.  Centralised so the scraper can be redirected to a
# fixture file in tests by monkeypatching this dict.
#
# Symbol convention for Canadian listings
# ---------------------------------------
# The Wikipedia TSX 60 / TSX Composite tables list bare TSX symbols
# (e.g., ``RY``).  Our storage convention adds a ``.TO`` suffix so the
# US ``RY`` (Royal Bank ADR on NYSE) and the TSX ``RY`` are stored as
# distinct ticker rows.  :func:`parse_constituent_table` appends the
# suffix for Canadian indices.
WIKIPEDIA_URLS: dict[str, str] = {
    "SP500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "NDX": "https://en.wikipedia.org/wiki/Nasdaq-100",
    "DJI": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
    "TSX60": "https://en.wikipedia.org/wiki/S%26P/TSX_60",
    "TSXC": "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index",
}

# Indices whose constituents are TSX-listed.  Parsed symbols from these
# pages get a ``.TO`` suffix appended to match our storage convention.
_TSX_INDEX_CODES: frozenset[str] = frozenset({"TSX60", "TSXC"})


def parse_constituent_table(html: str, index_code: str) -> list[ParsedMembership]:
    """Parse a Wikipedia constituent-list page into membership rows.

    Strategy
    --------
    1.  Find the first ``<table class="wikitable">`` whose header row
        contains a column literally named ``Symbol`` or ``Ticker``.
        Wikipedia uses both labels across its constituent pages.
    2.  Read each non-header row's first ``<td>`` as the ticker symbol.
    3.  Drop empty rows, rows missing a symbol, and rows whose "symbol"
        is suspiciously long (likely a multi-row merged cell — these
        signal a structural change we should investigate, not
        rows we should silently keep).

    Parameters
    ----------
    html
        Full HTML body of the Wikipedia article.
    index_code
        The Peach index code (e.g., ``"SP500"``) to stamp on each row.

    Returns
    -------
    list[ParsedMembership]
        One row per parsed constituent.  ``valid_from`` is set to today
        (call site can override if a more precise start date is known).
        ``valid_to`` is ``None`` — by definition these are "currently a
        member".
    """
    soup = BeautifulSoup(html, "lxml")
    today = utcnow().date()
    rows: list[ParsedMembership] = []
    # TSX-listed symbols get a ``.TO`` suffix so they don't collide with
    # any same-named US ticker in the unique ``tickers.symbol`` index.
    add_tsx_suffix = index_code in _TSX_INDEX_CODES

    for table in soup.find_all("table", class_="wikitable"):
        header = table.find("tr")
        if header is None:
            continue
        header_text = [th.get_text(strip=True) for th in header.find_all(["th", "td"])]
        # Locate the column index for "Symbol" or "Ticker" — Wikipedia
        # uses both across constituent tables.
        symbol_col_idx: int | None = None
        for idx, label in enumerate(header_text):
            if label.lower() in {"symbol", "ticker", "ticker symbol"}:
                symbol_col_idx = idx
                break
        if symbol_col_idx is None:
            continue  # not the constituent table — try the next one

        # Iterate over body rows (skip the header).
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) <= symbol_col_idx:
                continue
            symbol = cells[symbol_col_idx].get_text(strip=True)
            # Normalise: drop footnote markers like "AAPL[a]".
            if "[" in symbol:
                symbol = symbol.split("[", 1)[0].strip()
            if not symbol or len(symbol) > 12:
                # 12-char ceiling catches accidental merged-cell text
                # blobs without rejecting legitimate symbols like
                # "BRK.B" or "BF.B".
                continue
            # TSX rows get the ``.TO`` suffix only if not already present
            # (defensive — some Wikipedia pages render it inline).
            if add_tsx_suffix and not symbol.upper().endswith(".TO"):
                symbol = f"{symbol}.TO"
            rows.append(_membership(index_code, symbol, today))

        if rows:
            # Found a populated table — stop scanning further wikitables
            # on the page.  Some Wikipedia pages have multiple
            # ``wikitable`` instances (recent changes, historical
            # tables); we want only the canonical "current constituents"
            # one, which is reliably the first that matches.
            break

    log.info(
        "wikipedia.parse_complete",
        index_code=index_code,
        constituents=len(rows),
    )
    return rows


def _membership(index_code: str, symbol: str, today: date) -> ParsedMembership:
    """Build a ``ParsedMembership`` for a current constituent.

    Helper exists so the parser body stays focused on the table-walking
    logic and the construction is one obvious line.
    """
    return ParsedMembership(
        index_code=index_code,
        ticker_symbol=symbol,
        valid_from=today,
        valid_to=None,
        source=WikipediaMembershipSource.NAME,
    )


class WikipediaMembershipSource(DataSource):
    """The Wikipedia membership adapter exposed to the orchestrator."""

    NAME = "wikipedia"

    def __init__(self) -> None:
        """No state to initialise."""

    def fetch_current_members(self, index_code: str) -> Iterable[ParsedMembership]:
        """Scrape the current constituents of ``index_code`` from Wikipedia.

        Raises
        ------
        KeyError
            If the supplied ``index_code`` isn't one of SP500/NDX/DJI.
            The plan defines this universe explicitly — adding more
            indices is a deliberate schema-level decision.
        """
        url = WIKIPEDIA_URLS[index_code]
        log.info("wikipedia.fetch", index_code=index_code, url=url)
        html = fetch_text(url)
        return parse_constituent_table(html, index_code)


__all__: list[str] = [
    "WIKIPEDIA_URLS",
    "WikipediaMembershipSource",
    "parse_constituent_table",
]
