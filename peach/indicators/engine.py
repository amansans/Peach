"""Indicator engine — runs every registered indicator across the universe.

Two entry points:

* :func:`compute_for_ticker` — pure-function: given an OHLCV DataFrame,
  run every registered indicator and return a long-form values
  DataFrame.  Used by tests; does not touch the database.

* :func:`run_for_ticker` — loads OHLCV from ``ohlcv_daily``, computes
  every indicator, and upserts results into ``indicator_snapshots``.
  Used by the daily-EOD pipeline.

Both are intentionally per-ticker.  Indicators are per-time-series in
nature; batching across tickers complicates failure isolation more than
it speeds anything up at our scale.  If the engine becomes a bottleneck
later, parallelism happens at the ticker loop, not inside the indicators.
"""

from __future__ import annotations

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from peach.db.models.prices import OHLCVDaily
from peach.db.models.reference import Ticker
from peach.db.session import session_scope
from peach.indicators.registry import all_specs
from peach.indicators.snapshot_writer import upsert_indicator_rows

log = structlog.get_logger(__name__)


def load_ohlcv(session: Session, ticker_id: int) -> pd.DataFrame:
    """Return the full ``ohlcv_daily`` history for a ticker as a DataFrame.

    Columns: ``open``, ``high``, ``low``, ``close``, ``adj_close``,
    ``volume``.  Index is ``bar_date`` (a DatetimeIndex constructed from
    Python dates).  Rows are sorted ascending by date.

    Returns an empty DataFrame if no bars exist for that ticker — the
    caller is responsible for skipping the indicator pass in that case.
    """
    rows = session.execute(
        select(
            OHLCVDaily.bar_date,
            OHLCVDaily.open,
            OHLCVDaily.high,
            OHLCVDaily.low,
            OHLCVDaily.close,
            OHLCVDaily.adj_close,
            OHLCVDaily.volume,
        )
        .where(OHLCVDaily.ticker_id == ticker_id)
        .order_by(OHLCVDaily.bar_date)
    ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["bar_date", "open", "high", "low", "close", "adj_close", "volume"],
    )
    df = df.set_index("bar_date")
    # Decimal columns from Postgres come back as `decimal.Decimal`;
    # convert to float for numeric ops.  We re-cast to Decimal in the
    # writer to preserve precision on the way back out.
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        df[col] = df[col].astype(float)
    return df


def compute_for_ticker(df: pd.DataFrame, ticker_id: int) -> pd.DataFrame:
    """Run every registered indicator on ``df`` and return long-form rows.

    Parameters
    ----------
    df
        OHLCV DataFrame as returned by :func:`load_ohlcv`.
    ticker_id
        ID of the ticker whose history this is.  Stamped into each
        emitted row so the writer can route to the right rows.

    Returns
    -------
    pandas.DataFrame
        Long-form: columns ``ticker_id``, ``bar_date``, ``indicator_code``,
        ``value``.  May contain NaN values; the writer drops them.
    """
    if df.empty:
        return pd.DataFrame(columns=["ticker_id", "bar_date", "indicator_code", "value"])

    pieces: list[pd.DataFrame] = []
    for spec in all_specs():
        if spec.fn is None:  # pragma: no cover - registry guarantees this
            continue
        wide = spec.fn(df)
        # Convert wide (one column per produced code) to long.
        long = wide.stack().reset_index()
        long.columns = ["bar_date", "indicator_code", "value"]
        pieces.append(long)

    if not pieces:
        return pd.DataFrame(columns=["ticker_id", "bar_date", "indicator_code", "value"])

    combined = pd.concat(pieces, axis=0, ignore_index=True)
    combined.insert(0, "ticker_id", ticker_id)
    return combined


def run_for_ticker(ticker_id: int) -> int:
    """Load OHLCV, compute, and upsert indicators for one ticker.

    Returns the number of indicator rows upserted.  Returns 0 if the
    ticker has no OHLCV history (e.g., a stub row created by the
    membership writer for a ticker we haven't yet priced).
    """
    with session_scope() as session:
        df = load_ohlcv(session, ticker_id)
    if df.empty:
        log.info("engine.skip_no_ohlcv", ticker_id=ticker_id)
        return 0

    long_df = compute_for_ticker(df, ticker_id)
    # Restore DatetimeIndex values to Python date — Postgres `DATE`
    # columns reject pandas Timestamp objects with a tzinfo set.
    if not long_df.empty:
        long_df["bar_date"] = pd.to_datetime(long_df["bar_date"]).dt.date

    with session_scope() as session:
        return upsert_indicator_rows(session, long_df)


def run_for_all_tickers() -> int:
    """Run the engine for every ticker that has any OHLCV rows.

    Returns total indicator rows upserted across the batch.  Per-ticker
    failures are caught and logged so a single bad ticker doesn't
    abort the whole daily run.
    """
    with session_scope() as session:
        ticker_ids = list(
            session.scalars(
                select(Ticker.id)
                .join(OHLCVDaily, OHLCVDaily.ticker_id == Ticker.id)
                .distinct()
                .order_by(Ticker.id)
            ).all()
        )

    log.info("engine.run_all.start", n_tickers=len(ticker_ids))
    total = 0
    failed = 0
    for tid in ticker_ids:
        try:
            total += run_for_ticker(tid)
        except Exception as exc:
            failed += 1
            log.warning("engine.run_all.ticker_failed", ticker_id=tid, error=str(exc))
    log.info("engine.run_all.complete", n_tickers=len(ticker_ids), n_rows=total, n_failed=failed)
    return total


__all__: list[str] = [
    "compute_for_ticker",
    "load_ohlcv",
    "run_for_all_tickers",
    "run_for_ticker",
]
