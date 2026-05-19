"""Bulk upsert of indicator values into ``indicator_snapshots``.

Engine emits per-ticker, per-bar values as a long-form DataFrame
(columns: ``ticker_id``, ``bar_date``, ``indicator_code``, ``value``);
this module's :func:`upsert_indicator_rows` writes them with
``INSERT ... ON CONFLICT DO UPDATE`` so re-runs are idempotent.

NaN handling
------------
Indicators are intentionally undefined on warmup bars (e.g., SMA-200's
first 199 bars).  The writer drops those rows before insert — querying
"missing values" is a left join from ``ohlcv_daily``, not a NULL scan
of ``indicator_snapshots``.  Smaller table, cheaper joins.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from peach.db.models.indicators import IndicatorSnapshot

log = structlog.get_logger(__name__)


def upsert_indicator_rows(session: Session, long_df: pd.DataFrame) -> int:
    """Upsert a long-form indicator-values DataFrame.

    Expected columns: ``ticker_id`` (int), ``bar_date`` (date),
    ``indicator_code`` (str), ``value`` (numeric).

    Rows with NaN ``value`` are dropped before insert.  The conflict
    target is the composite PK ``(ticker_id, bar_date, indicator_code)``;
    ON CONFLICT DO UPDATE overwrites ``value`` so re-runs that produce
    different numbers (e.g., a fix to an indicator's math) correctly
    refresh the stored value.

    Parameters
    ----------
    session
        Active SQLAlchemy session.  Caller owns commit/rollback.
    long_df
        Long-form values.  May span multiple tickers and indicators.

    Returns
    -------
    int
        Number of rows actually upserted (after the NaN drop).
    """
    if long_df.empty:
        return 0

    # Drop undefined values — they would either fail NOT NULL or insert
    # noise.  We intentionally do NOT also drop inf/-inf here; that's
    # an indicator-implementation bug we want surfaced as a row that
    # the CHECK on NUMERIC range will reject.
    clean = long_df.dropna(subset=["value"]).copy()
    if clean.empty:
        return 0

    # Convert numerics to Python Decimal for psycopg.  pandas → numpy →
    # psycopg goes through float-binding which loses precision for the
    # wide cumulative indicators (OBV).  Going through Decimal is the
    # one path that preserves NUMERIC(28, 12) fidelity end-to-end.
    payload: list[dict[str, object]] = [
        {
            "ticker_id": int(row.ticker_id),
            "bar_date": row.bar_date,
            "indicator_code": str(row.indicator_code),
            "value": Decimal(str(row.value)),
        }
        for row in clean.itertuples(index=False)
    ]

    stmt = pg_insert(IndicatorSnapshot).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker_id", "bar_date", "indicator_code"],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)

    log.info(
        "indicator_writer.upserted",
        n_rows=len(payload),
        n_indicators=clean["indicator_code"].nunique(),
        n_tickers=clean["ticker_id"].nunique(),
    )
    return len(payload)


__all__: list[str] = ["upsert_indicator_rows"]
