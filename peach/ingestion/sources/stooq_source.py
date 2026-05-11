"""Stooq daily-OHLCV adapter.

Stooq is the primary OHLCV source per the architectural plan.  It is:

* free, with no API key;
* polite about rate limiting (1 request per second is more than safe);
* historically deep for US large caps (often 20+ years);
* split-adjusted but NOT dividend-adjusted — we treat its ``close`` as
  both ``close`` and ``adj_close`` in the database for v1, and Phase 5+
  recomputes ``adj_close`` from the EDGAR-derived dividend history.

URL shape
---------
::

    https://stooq.com/q/d/l/?s={symbol_lower}.us&i=d

Example::

    https://stooq.com/q/d/l/?s=aapl.us&i=d

The response is CSV with header ``Date,Open,High,Low,Close,Volume``.
Dates are ISO ``YYYY-MM-DD``.

Failure modes we tolerate
-------------------------
* **Empty response** — Stooq sometimes returns ``"No data"`` for very
  recent IPOs or for unknown symbols.  Treat as "no rows", not as an
  error; the orchestrator will fall back to yfinance for that ticker.
* **Half-trading days with blank Volume** — the parser drops these
  rather than insert a NULL violation against ``ohlcv_daily.volume``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

import structlog

from peach.ingestion.base import DataSource, ParsedOHLCV
from peach.ingestion.http import fetch_text

log = structlog.get_logger(__name__)


# Distinct sentinel Stooq returns when it has no history for a symbol.
# Observed in the wild as the literal string "No data".
_STOOQ_NO_DATA_MARKER = "No data"


def _build_url(symbol: str) -> str:
    """Translate a US equity symbol to its Stooq daily-CSV URL.

    Stooq uses lowercase symbols with a ``.us`` suffix.  Special-character
    symbols (BRK.B → brk-b.us) get a hyphen substitution.
    """
    # The hyphen-for-dot substitution matches Stooq's URL convention.
    canonical = symbol.lower().replace(".", "-")
    return f"https://stooq.com/q/d/l/?s={canonical}.us&i=d"


def parse_stooq_csv(content: str, symbol: str) -> list[ParsedOHLCV]:
    """Parse a Stooq daily-CSV payload into ``ParsedOHLCV`` rows.

    Parameters
    ----------
    content
        The full CSV body as returned by Stooq.  Caller is responsible
        for ensuring this is text (not bytes); :func:`fetch_text`
        already returns text.
    symbol
        The ticker symbol that was requested.  Stamped into each
        returned row's ``symbol`` field.

    Returns
    -------
    list[ParsedOHLCV]
        One row per non-empty, well-formed CSV line.  Returns an empty
        list if Stooq emitted its "No data" sentinel — that is an
        expected outcome for unknown / very-new symbols, not an error.

    Notes
    -----
    Stooq occasionally emits rows where ``Volume`` is empty (half-trading
    days, holidays partially traded).  Such rows are dropped — they
    would fail our ``ohlcv_daily.volume NOT NULL`` constraint and offer
    little analytical value as standalone bars.
    """
    # The "No data" marker is the only payload-shape we silently swallow.
    if not content or content.strip() == _STOOQ_NO_DATA_MARKER:
        log.info("stooq.no_data", symbol=symbol)
        return []

    rows: list[ParsedOHLCV] = []
    reader = csv.DictReader(io.StringIO(content))
    for raw in reader:
        # Stooq CSVs occasionally emit a trailing blank row; skip them.
        if not raw or not raw.get("Date"):
            continue

        # Half-trading days sometimes have empty Volume; skip rather than
        # insert garbage.  We log only at DEBUG because this is normal.
        volume_str = raw.get("Volume", "").strip()
        if not volume_str:
            log.debug("stooq.skip_empty_volume", symbol=symbol, date=raw["Date"])
            continue

        try:
            rows.append(
                ParsedOHLCV(
                    symbol=symbol,
                    bar_date=datetime.strptime(raw["Date"], "%Y-%m-%d").date(),
                    open=Decimal(raw["Open"]),
                    high=Decimal(raw["High"]),
                    low=Decimal(raw["Low"]),
                    close=Decimal(raw["Close"]),
                    # Stooq is split-adjusted only.  Setting adj_close =
                    # close here is the documented Phase 1 behavior; Phase
                    # 5+ recomputes true dividend-adjusted prices.
                    adj_close=Decimal(raw["Close"]),
                    volume=Decimal(volume_str),
                    source=StooqSource.NAME,
                )
            )
        except (ValueError, KeyError, ArithmeticError) as exc:
            # Don't blow up the whole batch on a single bad row — log
            # and move on.  Phase 1's data-quality job catches systemic
            # parse failures via the resulting row-count drop.
            log.warning(
                "stooq.parse_row_failed",
                symbol=symbol,
                date=raw.get("Date"),
                error=str(exc),
            )
            continue

    return rows


class StooqSource(DataSource):
    """The Stooq adapter exposed to the orchestrator."""

    NAME = "stooq"

    def __init__(self) -> None:
        """No-op constructor — Stooq is stateless from our perspective."""

    def fetch_ohlcv(self, symbol: str, start: date, end: date) -> Iterable[ParsedOHLCV]:
        """Return OHLCV rows for ``symbol`` in ``[start, end]``.

        Stooq's URL does not accept date-range parameters — it always
        returns the full history.  We fetch once and filter in memory.
        That's still cheap (a 20-year payload is ~150 KB).
        """
        url = _build_url(symbol)
        log.info("stooq.fetch", symbol=symbol, url=url)
        body = fetch_text(url)
        rows = parse_stooq_csv(body, symbol)
        # Inclusive [start, end] window.
        return [r for r in rows if start <= r.bar_date <= end]


__all__: list[str] = ["StooqSource", "parse_stooq_csv"]
