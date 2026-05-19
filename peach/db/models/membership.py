"""Point-in-time index membership — the survivorship-bias defense.

Why this table exists
---------------------
Every backtest must answer "who was in the SP500 on 2020-03-23?" — not
"who is in the SP500 today and happens to have data going back to
2020-03-23?".  Filtering on the latter biases results upward because
delisted tickers (Lehman, Bear Stearns, MCI WorldCom, Sears, …) are
silently excluded.

The fix is a bitemporal-ish table:

* ``valid_from`` — the first date this ticker was a member of this index.
* ``valid_to``   — the last date (NULL means "still a member today").

Membership-as-of-T is then::

    SELECT ticker_id
    FROM   index_memberships
    WHERE  index_id  = :index_id
      AND  valid_from <= :as_of
      AND  (valid_to IS NULL OR valid_to >= :as_of)

The plan caveats this table aggressively: Wikipedia revision history fills
in the past (best-effort), and issuer-ETF holdings CSVs (IVV / QQQ / DIA)
provide the ongoing ground truth from the day this project goes live.
*History from this point forward is yours.*

What this table is NOT
----------------------
* It is not a weights table — index *weights* change daily; we only track
  in/out, which changes ~monthly.  Weights aren't useful for the
  equal-weight buy-the-hit screener pattern we're building.
* It is not a price table — `ohlcv_daily` is the price source.  A ticker
  can have OHLCV rows for dates outside its membership window (e.g., the
  pre-IPO trading on its first listed day) without being a member.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peach.db.base import Base, TimestampMixin
from peach.db.models.reference import Index, Ticker


class IndexMembership(Base, TimestampMixin):
    """A single (index, ticker) membership period.

    Multiple rows can exist for the same (index_id, ticker_id) pair — for
    example, GE was removed from the Dow in 2018 and re-added in 2024,
    producing two distinct membership periods.  The composite uniqueness
    constraint is therefore on ``(index_id, ticker_id, valid_from)``
    rather than on ``(index_id, ticker_id)``.
    """

    __tablename__ = "index_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FK to indices.id.  ON DELETE RESTRICT means an index cannot be
    # deleted while membership history exists — historical correctness
    # outweighs the convenience of `DELETE FROM indices WHERE ...`.
    index_id: Mapped[int] = mapped_column(
        ForeignKey("indices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    index: Mapped[Index] = relationship()

    # FK to tickers.id.  ON DELETE CASCADE because a ticker truly gone from
    # the schema (e.g., a data-error duplicate row) should not leave
    # orphaned membership rows.  In practice we soft-delete tickers via
    # `is_active=False` instead.
    ticker_id: Mapped[int] = mapped_column(
        ForeignKey("tickers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[Ticker] = relationship()

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)

    # NULL means "still a member as of the most recent ingest".  Set to a
    # concrete date when a ticker is removed.  We do NOT auto-set this
    # column to "today minus 1" — that would corrupt historical queries.
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Where this row came from.  Useful when reconciling discrepancies.
    # Free-form to keep the column small; recommended values:
    #   "wikipedia"        — scraped from Wikipedia article HTML
    #   "wikipedia_history"— parsed from Wikipedia revision history
    #   "ishares_ivv"      — BlackRock IVV daily holdings CSV
    #   "ishares_dia"      — BlackRock DIA daily holdings CSV
    #   "invesco_qqq"      — Invesco QQQ daily holdings CSV
    #   "manual"           — operator-entered correction
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        # A given (index, ticker) pair cannot have two membership periods
        # starting on the same date.  This is the natural-key uniqueness.
        UniqueConstraint("index_id", "ticker_id", "valid_from", name="period_per_index_ticker"),
        # Sanity check: valid_to (when set) cannot precede valid_from.
        # The `OR valid_to IS NULL` half accommodates open-ended rows.
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_ordered"),
    )


__all__: list[str] = ["IndexMembership"]
