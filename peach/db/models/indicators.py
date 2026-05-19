"""Indicator catalog + per-bar snapshot table.

Two tables, one job
-------------------
* :class:`IndicatorCatalog` is the *metadata* — one row per
  ``indicator_code`` we know how to compute, plus the family / component
  / parameter dict that the UI uses to group MACD's three components or
  Bollinger's four into a single visual indicator.

* :class:`IndicatorSnapshot` is the *value* — one row per
  ``(ticker_id, bar_date, indicator_code)``, storing the computed value
  as ``NUMERIC(28, 12)``.  The wide precision matters because cumulative
  indicators (OBV, A/D Line) can grow into the billions while still
  needing post-decimal precision for accurate slope calculations later.

Why a single value column rather than a typed JSONB blob?
---------------------------------------------------------
* Postgres aggregates and range scans over numeric columns are dramatically
  faster than over JSONB extracts — and the screener layer (Phase 3) is
  cross-section-heavy ("every ticker where RSI<30 today").
* Multi-component indicators are handled by exploding into multiple
  ``indicator_code`` rows (e.g., ``macd_12_26_9_line``, ``_signal``,
  ``_hist``).  The catalog's ``family`` column lets the UI group them
  for plotting; the storage shape stays uniformly tabular.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peach.db.base import Base, TimestampMixin
from peach.db.models.reference import Ticker


# ---------------------------------------------------------------------------
# Indicator catalog (metadata)
# ---------------------------------------------------------------------------
class IndicatorCatalog(Base, TimestampMixin):
    """One row per ``indicator_code`` we know how to compute.

    Seeded from :mod:`scripts.seed_indicators`, which iterates the
    in-code registry (``peach.indicators.registry``) and upserts a row
    per registered code.  Keeping the catalog in the DB (rather than
    only in code) gives the UI a stable join target for free-form
    queries like "show me every momentum indicator".

    ``params_json`` records the parameter dict used to compute the
    indicator (e.g., ``{"window": 14}`` for RSI-14).  The screener YAML
    layer references indicators by ``code`` exclusively, so changes to
    params_json never break existing rule sets — adding a new code is
    the path for a new parameter set.
    """

    __tablename__ = "indicators_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The canonical identifier used as the FK target from
    # ``indicator_snapshots.indicator_code``.  Stable across releases —
    # changing a code is a migration, not a config tweak.
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Logical grouping for UI display.  Example: ``macd_12_26_9_line``,
    # ``_signal``, and ``_hist`` all share ``family = "macd_12_26_9"``.
    family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Per-family component label (``line``, ``signal``, ``hist``,
    # ``upper``, ``mid``, ``lower``…).  NULL for single-component
    # indicators like RSI.
    component: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Human-readable category — matches the plan's grouping:
    # ``trend`` / ``momentum`` / ``volume`` / ``volatility`` / ``support_resistance``.
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # The parameter dict that produced this indicator, serialised JSON.
    # Examples: ``{"window": 14}``, ``{"fast": 12, "slow": 26, "signal": 9}``.
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Schema version for the *math* behind this code.  Bumped when an
    # implementation bug fix changes outputs — lets us rebuild affected
    # snapshots without ambiguity.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Indicates whether this code is currently computed by the engine.
    # An indicator can be deprecated by setting `is_active = False`
    # without losing historical snapshots.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------------------------------------------------------------------
# Indicator snapshot (per-bar values)
# ---------------------------------------------------------------------------
class IndicatorSnapshot(Base, TimestampMixin):
    """One indicator value per (ticker, bar_date, indicator_code).

    The schema deliberately mirrors :class:`peach.db.models.prices.OHLCVDaily`
    in PK shape (composite, ticker-first) for index locality.  Phase 3's
    screener engine reads this table heavily — both per-ticker time series
    ("last 200 days of RSI for AAPL") and cross-section ("RSI < 30 across
    the universe today").

    ``value`` is ``NUMERIC(28, 12)`` — wide enough for cumulative
    indicators (OBV can reach 10^13 for the big names) while preserving
    fractional precision for ratios like RSI.

    NULL handling
    -------------
    Some indicators are undefined for the first N bars (e.g., SMA-200
    needs 200 prior closes).  The engine simply does not insert a row
    for those bars; querying for "missing values" is a left-join from
    ``ohlcv_daily``.  This is cheaper than storing explicit NULLs
    everywhere.
    """

    __tablename__ = "indicator_snapshots"

    ticker_id: Mapped[int] = mapped_column(
        ForeignKey("tickers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ticker: Mapped[Ticker] = relationship()

    bar_date: Mapped[date] = mapped_column(Date, primary_key=True)

    indicator_code: Mapped[str] = mapped_column(
        ForeignKey("indicators_catalog.code", ondelete="CASCADE"),
        primary_key=True,
    )

    value: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)


__all__: list[str] = ["IndicatorCatalog", "IndicatorSnapshot"]
