"""Reference data tables — small, mostly-static rows the rest of the
schema points at via foreign keys.

Contents
--------
* :class:`Exchange` — XNAS, XNYS, ARCA, etc.
* :class:`Sector`   — GICS sector taxonomy.  Self-referential so it can hold
                      sectors, industry groups, industries, and sub-industries
                      under one table with a `parent_id` link.
* :class:`Index`    — The market indices we screen: SP500, NDX, DJI.
* :class:`Ticker`   — Equity tickers.  This is the central reference table:
                      OHLCV, fundamentals, indicators, screener hits, etc.
                      all FK to `tickers.id`.
* :class:`TickerAlias` — Historical symbol changes (e.g., TWTR → X).  Lets
                          us look up a ticker by any symbol it has ever had.

What this module does NOT contain
---------------------------------
Time-series tables (`ohlcv_daily`, `fundamentals_facts`, `indicator_snapshots`,
…) live in their own modules per phase.  Membership history
(`index_memberships`) is a separate module because its point-in-time
semantics warrant their own home.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peach.db.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Exchanges
# ---------------------------------------------------------------------------
class Exchange(Base, TimestampMixin):
    """An equity exchange (e.g., XNAS = Nasdaq, XNYS = NYSE).

    Static reference data.  Codes follow the ISO 10383 MIC standard so
    they're unambiguous across data sources.
    """

    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # MIC (Market Identifier Code).  4 chars, e.g., "XNAS".
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)

    # Human-readable name.
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # ISO 3166-1 alpha-2 country code of the exchange itself (e.g., "US"
    # for XNAS/XNYS, "CA" for XTSE).  This is the canonical hook for
    # the US-vs-Canadian-stocks filter — joining ``tickers → exchanges
    # → country_code`` is unambiguous (the *listing* country, regardless
    # of where the issuer is headquartered).
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # Reverse relationship — populated by `Ticker.exchange`.  Useful for
    # admin pages that list "all tickers on XNAS" without an explicit join.
    tickers: Mapped[list[Ticker]] = relationship(
        back_populates="exchange",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# GICS Sector taxonomy
# ---------------------------------------------------------------------------
class Sector(Base, TimestampMixin):
    """A node in the GICS classification tree.

    GICS is a 4-level hierarchy:
        Sector → Industry Group → Industry → Sub-Industry

    Rather than four separate tables, we model it as a single self-referential
    table with a `parent_id` pointer.  This:

    * mirrors the source data (S&P / MSCI publish GICS as a parent/child
      taxonomy with stable numeric codes);
    * lets us join `Ticker.sub_industry` and recursively reach its parent
      sector without four LEFT JOINs;
    * is the schema EDGAR / iShares CSVs / Wikipedia all produce naturally.

    The `level` column (1..4) lets us filter "give me all sectors" without
    walking the parent chain.
    """

    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # GICS code — 2 digits for sector, 4 for industry group, 6 for industry,
    # 8 for sub-industry.  Stored as string because leading zeros matter
    # ("10" = Energy is not "10.0").
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 1 = Sector, 2 = Industry Group, 3 = Industry, 4 = Sub-Industry.
    # A CHECK constraint enforces the range.
    level: Mapped[int] = mapped_column(Integer, nullable=False)

    # Self-referential FK.  Level-1 (sector) rows have `parent_id = NULL`.
    # Deleting a parent cascades to children — when GICS is re-seeded we
    # want a clean replacement, not orphaned sub-industries pointing into
    # the void.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sectors.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # SQLAlchemy self-referential relationship — `remote_side` tells the ORM
    # which side of the FK is the "parent" so it can correctly populate the
    # `children` collection without infinite recursion.
    parent: Mapped[Sector | None] = relationship(
        "Sector",
        remote_side="Sector.id",
        back_populates="children",
    )
    children: Mapped[list[Sector]] = relationship(
        "Sector",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Constrain level to the valid GICS depth range (1=sector through
        # 4=sub-industry).  Catches bootstrap typos before they corrupt
        # downstream peer-group logic.  The constraint name follows the
        # `ck_<table>_<name>` pattern set by NAMING_CONVENTION in db.base.
        CheckConstraint("level BETWEEN 1 AND 4", name="level_range"),
    )


# ---------------------------------------------------------------------------
# Indices we screen
# ---------------------------------------------------------------------------
class Index(Base, TimestampMixin):
    """A market index whose constituents we track.

    Rows in v1:
        SP500  — S&P 500                                       (US)
        NDX    — Nasdaq-100                                    (US)
        DJI    — Dow Jones Industrial Average                  (US)
        TSX60  — S&P/TSX 60                                    (CA)
        TSXC   — S&P/TSX Composite                             (CA)

    The *constituents* of each index are stored in `index_memberships`
    (Phase 1) with `valid_from` / `valid_to` so we can answer "who was in
    the SP500 on 2020-03-23?" — the core defense against survivorship bias
    in backtests.
    """

    __tablename__ = "indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Where the constituent data comes from.  "spglobal" for SP500/DJI,
    # "nasdaq" for NDX, or "ishares" / "invesco" if we use the issuer ETF
    # holdings as the ground truth (recommended for ongoing tracking).
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # ISO 3166-1 alpha-2 country code of the index's home market.  Used
    # by ingestion to:
    # (a) pick the default listing exchange for a new ticker stub
    #     (US-only indices → XNAS; CA-only indices → XTSE);
    # (b) pick the right Stooq URL suffix (.us vs .ca) and the right
    #     yfinance symbol suffix (.TO for TSX).
    # `country_code='US'` for SP500/NDX/DJI; `country_code='CA'` for
    # TSX60/TSXC.
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)


# ---------------------------------------------------------------------------
# Tickers — the central reference table
# ---------------------------------------------------------------------------
class Ticker(Base, TimestampMixin):
    """An equity ticker.

    Every other domain table (prices, fundamentals, indicators, screener
    hits, …) links here via FK to `tickers.id`.  Using a surrogate integer
    PK (rather than the ticker symbol itself) protects downstream tables
    from ticker symbol changes (e.g., TWTR → X) — historical symbols are
    captured in :class:`TickerAlias`.

    The `founded_year`, `ipo_date`, and `headquarters_country` columns
    power the company-age / years-public view on the Peer Comparison page
    (Phase 6).
    """

    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The *current* symbol (e.g., "AAPL").  Mutates over time, hence
    # `ticker_aliases` holding the historical record.
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Exchange the ticker is primary-listed on.
    exchange_id: Mapped[int] = mapped_column(
        ForeignKey("exchanges.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    exchange: Mapped[Exchange] = relationship(back_populates="tickers")

    # *Current* GICS sub-industry (the deepest GICS level).  Stored at the
    # leaf so peer-group queries can walk up the tree to sector or
    # industry-group level when needed.  Nullable because some early-load
    # tickers may arrive without a GICS classification.
    sub_industry_id: Mapped[int | None] = mapped_column(
        ForeignKey("sectors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # SEC Central Index Key — the canonical SEC identifier.  10-digit
    # zero-padded string when present.  Required for EDGAR fundamentals
    # ingestion in Phase 5 but optional here so we can seed tickers before
    # we know all their CIKs.
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    # OpenFIGI ID — useful for de-dup across data vendors that use different
    # symbology.  Optional.
    figi: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # `is_active` lets us soft-deactivate delisted tickers without losing
    # their history.  Backtests filter by active-at-time using the
    # `index_memberships` table; this flag is for UI convenience.
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    # When we first ingested a row for this symbol, and the most recent
    # date we saw activity.  Useful for orphan detection.
    first_seen: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_seen: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Company-age columns -- power the Peer Comparison page.
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    headquarters_country: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )  # ISO 3166-1 alpha-2

    aliases: Mapped[list[TickerAlias]] = relationship(
        back_populates="ticker",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Historical symbol aliases
# ---------------------------------------------------------------------------
class TickerAlias(Base, TimestampMixin):
    """Past or alternative symbols for a ticker.

    Why: tickers change.  TWTR → X.  FB → META.  When we see a historical
    rule hit referencing "TWTR" in a backtest, we want to resolve it back
    to the same `ticker_id` as today's "X".

    `valid_from` / `valid_to` capture the period during which the alias was
    the *current* trading symbol.  `valid_to IS NULL` means the alias is
    still the current symbol (rare — the `Ticker.symbol` column is the
    usual current-symbol source).
    """

    __tablename__ = "ticker_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    ticker_id: Mapped[int] = mapped_column(
        ForeignKey("tickers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[Ticker] = relationship(back_populates="aliases")

    alias: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        # An alias is unique per ticker per start date.  This guards against
        # double-inserting the same alias if an ingestion job re-runs.
        UniqueConstraint("ticker_id", "alias", "valid_from", name="alias_per_ticker_period"),
    )


__all__: list[str] = ["Exchange", "Index", "Sector", "Ticker", "TickerAlias"]
