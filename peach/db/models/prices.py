"""Daily OHLCV bars and corporate actions.

Why two tables
--------------
* ``ohlcv_daily`` stores the *as-of-today* split-and-dividend-adjusted
  prices.  This is what charts, indicators, and backtests read.

* ``corporate_actions`` stores the events that mutate the adjustment
  factor — splits and dividends.  Keeping them in their own table means a
  later re-adjustment (e.g., recomputing adj_close after an
  out-of-band split correction) is a `DELETE FROM ohlcv_daily WHERE ...`
  + re-fetch, not a multi-table reconciliation.

Why ``(ticker_id, bar_date)`` as a composite PK
-----------------------------------------------
A 5-year x 530-ticker window is ~670 k rows.  A composite PK on
``(ticker_id, bar_date)`` gives Postgres a clustered-ish layout: queries
of the form "give me AAPL's last 200 days" hit a single contiguous range
of index entries.  No surrogate `id` column is needed — bloat is real at
multi-million-row scale.

A BRIN index on ``bar_date`` is added in the migration for
cross-sectional queries ("all closes on 2020-03-23") — BRIN is the right
index type for naturally time-ordered tables.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peach.db.base import Base, TimestampMixin
from peach.db.models.reference import Ticker


# ---------------------------------------------------------------------------
# Daily bars
# ---------------------------------------------------------------------------
class OHLCVDaily(Base, TimestampMixin):
    """One end-of-day bar per (ticker, date).

    Prices are stored as `NUMERIC(20, 6)` (via SQLAlchemy's
    :class:`sqlalchemy.Numeric` type).  Floating-point types would lose
    pennies under cumulative arithmetic.

    Two close columns
    -----------------
    * ``close``     — the raw exchange close.  Useful for tooltips and
                      "what did AAPL close at on this date?" queries.
    * ``adj_close`` — the split-and-dividend-adjusted close.  This is the
                      column indicators and backtests read.  Recomputed
                      from ``corporate_actions`` whenever adjustments
                      change.
    """

    __tablename__ = "ohlcv_daily"

    # Composite PK.  Order matters for index locality: ticker first so
    # per-ticker range scans are cheap.
    ticker_id: Mapped[int] = mapped_column(
        ForeignKey("tickers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ticker: Mapped[Ticker] = relationship()

    bar_date: Mapped[date] = mapped_column(Date, primary_key=True)

    # The four price fields plus volume.  All NOT NULL because a bar with
    # any missing field is meaningless; data-quality job rejects them at
    # ingest time.
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    adj_close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    # Volume is integer-valued at the exchange but vendors sometimes
    # emit fractional volume after aggregation; use NUMERIC to be safe.
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 0), nullable=False)

    # Which data source produced this bar.  Distinct values so we can
    # avoid mixing sources within a single ticker's history (the plan's
    # explicit guidance).  Examples: "stooq", "yfinance", "yfinance_gapfill".
    source: Mapped[str] = mapped_column(String(32), nullable=False)


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------
class CorporateAction(Base, TimestampMixin):
    """A split, dividend, or spin-off event.

    ``kind`` is a free-form string rather than a Postgres ENUM because the
    set of action kinds will grow over time (rights issues, special
    distributions, name changes that aren't symbol changes…).  A CHECK
    constraint pins the *currently supported* values in the migration —
    adding a new value is a one-line CHECK update + migration, not a
    full ENUM ALTER TYPE.

    ``ratio`` is used for splits (e.g., 2-for-1 → 2.0; 1-for-10 reverse → 0.1).
    ``cash_amount`` is used for dividends (per-share, in the security's
    listing currency).

    Splits without dividends will have ``cash_amount IS NULL``; dividends
    without splits will have ``ratio = 1.0``.
    """

    __tablename__ = "corporate_actions"

    # Surrogate PK — corporate actions are intrinsically multi-row per
    # (ticker, date) (an ex-div date can also be a split date), so a
    # composite natural key isn't quite right.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    ticker_id: Mapped[int] = mapped_column(
        ForeignKey("tickers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[Ticker] = relationship()

    # Ex-action date (the date on which the action takes effect for
    # adjustment purposes).
    action_date: Mapped[date] = mapped_column(Date, nullable=False)

    # See class docstring; CHECK constraint in the migration pins the
    # allowed set.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    # Split / spin-off ratio.  Default 1.0 means "no price-scaling effect".
    ratio: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=Decimal("1"))

    # Per-share cash for dividends; NULL for non-cash actions.
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    # Originating source, same convention as `OHLCVDaily.source`.
    source: Mapped[str] = mapped_column(String(32), nullable=False)


__all__: list[str] = ["CorporateAction", "OHLCVDaily"]
