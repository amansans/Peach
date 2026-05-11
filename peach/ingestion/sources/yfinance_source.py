"""yfinance OHLCV adapter — used as a gap-fill fallback only.

The plan is explicit: Stooq is the primary OHLCV source.  yfinance is
called only when Stooq returns no data or a data-quality job detects a
gap.  Reasons we don't use yfinance as primary:

* Yahoo's underlying endpoints are unofficial and rate-limit
  unpredictably — they will occasionally just stop responding for a few
  minutes.
* The package's behavior across versions is fragile (column names,
  empty-DataFrame edge cases).
* True dividend-adjusted ``Adj Close`` from Yahoo is the one advantage,
  and it isn't strong enough to risk an unreliable primary feed.

Rows emitted by this source set ``source = "yfinance_gapfill"`` so a
``SELECT source, count(*) FROM ohlcv_daily GROUP BY source`` query can
audit how much of the dataset is fallback-sourced.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from peach.ingestion.base import DataSource, ParsedOHLCV

if TYPE_CHECKING:
    # Defer the heavy yfinance import to runtime — keeps `import peach`
    # fast even though yfinance itself drags in pandas + numpy.
    import pandas as pd  # noqa: F401

log = structlog.get_logger(__name__)


def _parse_yfinance_dataframe(df: Any, symbol: str) -> list[ParsedOHLCV]:
    """Translate the DataFrame yfinance returns into ``ParsedOHLCV`` rows.

    yfinance's DataFrame columns are ``Open / High / Low / Close /
    Adj Close / Volume``.  The index is timezone-aware datetimes; we
    take the ``.date()``.

    Empty DataFrames (yfinance's normal "no data" return) yield an
    empty list — same contract as Stooq's "No data" sentinel.
    """
    if df is None or df.empty:
        log.info("yfinance.no_data", symbol=symbol)
        return []

    rows: list[ParsedOHLCV] = []
    for ts, raw in df.iterrows():
        try:
            # `ts` is a pandas Timestamp.  We accept any object that has
            # a `.date()` method or can be normalised to one.
            bar_dt = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])

            # Volume can be NaN on partial-trading days — same handling
            # as the Stooq parser.
            volume_raw = raw.get("Volume")
            if volume_raw is None or volume_raw != volume_raw:  # NaN check
                continue

            rows.append(
                ParsedOHLCV(
                    symbol=symbol,
                    bar_date=bar_dt,
                    open=Decimal(str(raw["Open"])),
                    high=Decimal(str(raw["High"])),
                    low=Decimal(str(raw["Low"])),
                    close=Decimal(str(raw["Close"])),
                    # yfinance provides true dividend-adjusted close as
                    # `Adj Close` — this is the one value yfinance has
                    # that Stooq doesn't.
                    adj_close=Decimal(str(raw.get("Adj Close", raw["Close"]))),
                    volume=Decimal(str(int(volume_raw))),
                    source=YFinanceSource.NAME,
                )
            )
        except (ValueError, KeyError, ArithmeticError) as exc:
            log.warning(
                "yfinance.parse_row_failed",
                symbol=symbol,
                error=str(exc),
            )
            continue

    return rows


class YFinanceSource(DataSource):
    """yfinance adapter — gap-fill fallback only."""

    NAME = "yfinance_gapfill"

    def __init__(self) -> None:
        """No-op — yfinance state lives in the library, not in us."""

    def fetch_ohlcv(self, symbol: str, start: date, end: date) -> Iterable[ParsedOHLCV]:
        """Fetch [start, end] OHLCV via yfinance.

        Notes
        -----
        yfinance treats the ``end`` parameter as *exclusive*, so we add
        one day to keep our APIs uniformly inclusive.
        """
        # Lazy import — keeps `import peach` cheap and lets tests stub
        # out the dependency by monkeypatching this module.
        import yfinance as yf

        log.info("yfinance.fetch", symbol=symbol, start=str(start), end=str(end))
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=str(start),
            # +1 day to make our [start, end] inclusive match yfinance's
            # exclusive `end`.
            end=str(end + timedelta(days=1)),
            auto_adjust=False,  # keep raw + adj separate
            actions=False,  # we ingest splits/dividends separately
        )
        return _parse_yfinance_dataframe(df, symbol)


__all__: list[str] = ["YFinanceSource"]
