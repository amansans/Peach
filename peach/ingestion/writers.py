"""Idempotent writers: ``ParsedRow`` → database rows.

Why writers, not "let the orchestrator call session.add"
-------------------------------------------------------
* The unique constraints differ per table (composite PK on OHLCV; natural
  triple on membership).  Centralising them keeps the upsert idiom in
  one place.
* Pylint-grade `INSERT ... ON CONFLICT DO UPDATE` for the price path is
  ~6x faster than ORM-by-ORM upserts at 670 k rows.  Tucking the SQL
  here keeps callers oblivious.
* Re-running an ingest must NEVER double-count.  Centralised writers are
  the right place to make that property absolute and testable.
"""

from __future__ import annotations

from collections.abc import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from peach.db.models.membership import IndexMembership
from peach.db.models.prices import OHLCVDaily
from peach.db.models.reference import Exchange, Index, Ticker
from peach.ingestion.base import ParsedMembership, ParsedOHLCV

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Symbol → ticker_id resolution
# ---------------------------------------------------------------------------


def _ensure_default_exchange_id(session: Session) -> int:
    """Return an exchange_id we can attach to brand-new tickers.

    In Phase 1 we don't yet know the listing exchange for tickers
    discovered via membership scraping.  Rather than guess, we attach
    every new ticker to XNAS (placeholder).  Phase 5+ enrichment will
    correct the exchange via SEC / OpenFIGI lookup.

    Why a function call rather than a module-level constant?  The seeded
    row IDs are not stable across database resets — looking them up by
    code is the only reliable path.
    """
    exchange = session.scalars(select(Exchange).where(Exchange.code == "XNAS")).first()
    if exchange is None:  # pragma: no cover - seed script enforces this
        raise RuntimeError(
            "XNAS exchange row missing — run `make seed` to bootstrap reference data."
        )
    return exchange.id


def resolve_or_create_ticker(session: Session, symbol: str) -> Ticker:
    """Look up a ``Ticker`` by symbol; create a stub row if missing.

    Stub rows are deliberately minimal:

    * ``name`` defaults to the symbol — better than NULL, gets enriched
      by Phase 5 EDGAR ingestion;
    * ``exchange_id`` falls back to XNAS placeholder;
    * ``is_active`` defaults to True.

    This function exists because ingestion learns about new tickers
    *before* the operator manually curates them — a SP500 reconstitution
    can add a ticker we've never seen, and we need to ingest its prices
    on the same daily run.

    Parameters
    ----------
    session
        Active SQLAlchemy session.  The caller is responsible for commit /
        rollback.
    symbol
        Equity symbol.  Lookups are case-sensitive against the
        ``tickers.symbol`` column — Phase 1 always uses uppercase.

    Returns
    -------
    Ticker
        Either the existing row or the newly-inserted stub.
    """
    existing = session.scalars(select(Ticker).where(Ticker.symbol == symbol)).first()
    if existing is not None:
        return existing

    log.info("writers.ticker_stub_created", symbol=symbol)
    stub = Ticker(
        symbol=symbol,
        name=symbol,
        exchange_id=_ensure_default_exchange_id(session),
        is_active=True,
    )
    session.add(stub)
    # Flush so the row gets an `id` that callers can reference in the
    # same transaction — without this, downstream FK inserts would
    # fail until commit.
    session.flush()
    return stub


# ---------------------------------------------------------------------------
# OHLCV writer
# ---------------------------------------------------------------------------


def upsert_ohlcv_rows(session: Session, rows: Iterable[ParsedOHLCV]) -> int:
    """Insert (or update) a batch of daily bars.

    Uses Postgres ``INSERT ... ON CONFLICT (ticker_id, bar_date) DO UPDATE``
    so:

    * a re-run of the same ingest is a no-op (idempotent);
    * a corrected re-fetch (different ``adj_close`` after corporate-action
      enrichment) updates the row in place rather than failing on PK
      collision.

    Parameters
    ----------
    session
        Active SQLAlchemy session.
    rows
        Iterable of parsed rows.  May span multiple tickers.

    Returns
    -------
    int
        Number of input rows passed to the upsert.  This is NOT the same
        as the number of *new* DB rows — that's hard to know without
        a `RETURNING xmax = 0` trick, and the caller usually only cares
        about throughput-style counts.

    Notes
    -----
    The function resolves each unique ``symbol`` to a ``ticker_id`` on
    the fly via :func:`resolve_or_create_ticker`.  Repeated lookups for
    the same symbol within one batch are deduplicated.
    """
    rows = list(rows)
    if not rows:
        return 0

    # Cache symbol → ticker_id across the batch to avoid repeated SELECTs.
    symbol_to_id: dict[str, int] = {}
    for row in rows:
        if row.symbol not in symbol_to_id:
            symbol_to_id[row.symbol] = resolve_or_create_ticker(session, row.symbol).id

    payload: list[dict[str, object]] = [
        {
            "ticker_id": symbol_to_id[r.symbol],
            "bar_date": r.bar_date,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "adj_close": r.adj_close,
            "volume": r.volume,
            "source": r.source,
        }
        for r in rows
    ]

    stmt = pg_insert(OHLCVDaily).values(payload)
    # On conflict (composite PK), overwrite the mutable columns.  We
    # *don't* overwrite `created_at`; `updated_at` is auto-bumped via the
    # ORM `onupdate=func.now()` hook (which still fires for SQL-level
    # upserts thanks to the column's `server_default`/`onupdate` pair).
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker_id", "bar_date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "adj_close": stmt.excluded.adj_close,
            "volume": stmt.excluded.volume,
            "source": stmt.excluded.source,
        },
    )
    session.execute(stmt)
    log.info("writers.ohlcv_upserted", n_rows=len(rows), n_tickers=len(symbol_to_id))
    return len(rows)


# ---------------------------------------------------------------------------
# Membership writer
# ---------------------------------------------------------------------------


def sync_current_memberships(
    session: Session,
    index_code: str,
    rows: Iterable[ParsedMembership],
) -> tuple[int, int, int]:
    """Reconcile a fresh "current members" list with the membership table.

    The reconciliation logic is the heart of the survivorship-bias
    defense, so it's documented carefully:

    1.  Open the current open-ended period (``valid_to IS NULL``) for
        every ticker already in the index.  Call this set ``had``.

    2.  Compute ``now`` = set of tickers in the fresh ``rows`` list.

    3.  For each ticker in ``now - had`` (newly added today): insert a
        new membership row with ``valid_from = today``, ``valid_to = NULL``.

    4.  For each ticker in ``had - now`` (removed today): set ``valid_to =
        today - 1`` on the existing open-ended row, closing the period.

    5.  Leave existing open-ended rows for tickers in ``had & now``
        unchanged.  The plan's "history from this point forward is yours"
        principle relies on never rewriting a ``valid_from`` once set.

    Returns
    -------
    tuple[int, int, int]
        ``(n_kept, n_added, n_removed)`` for logging / observability.
    """
    rows = list(rows)
    today = rows[0].valid_from if rows else None
    if today is None:
        log.warning("writers.sync_membership_empty", index_code=index_code)
        return (0, 0, 0)

    # Resolve index_code -> index.id.
    index_obj = session.scalars(select(Index).where(Index.code == index_code)).first()
    if index_obj is None:  # pragma: no cover - bootstrap enforces this
        raise RuntimeError(f"Index {index_code!r} not found — run `make seed` to bootstrap.")

    # Map fresh symbols -> ticker rows (creating stubs as needed).
    fresh_tickers: dict[str, Ticker] = {}
    for r in rows:
        if r.ticker_symbol not in fresh_tickers:
            fresh_tickers[r.ticker_symbol] = resolve_or_create_ticker(session, r.ticker_symbol)

    # Current open-ended memberships for this index.
    open_periods = (
        session.scalars(
            select(IndexMembership).where(
                IndexMembership.index_id == index_obj.id,
                IndexMembership.valid_to.is_(None),
            )
        )
    ).all()
    had_by_ticker_id: dict[int, IndexMembership] = {m.ticker_id: m for m in open_periods}

    now_ticker_ids: set[int] = {t.id for t in fresh_tickers.values()}
    had_ticker_ids: set[int] = set(had_by_ticker_id.keys())

    n_added = 0
    for ticker in fresh_tickers.values():
        if ticker.id in had_ticker_ids:
            continue  # still a member, no-op
        session.add(
            IndexMembership(
                index_id=index_obj.id,
                ticker_id=ticker.id,
                valid_from=today,
                valid_to=None,
                source=rows[0].source,
            )
        )
        n_added += 1

    n_removed = 0
    for ticker_id in had_ticker_ids - now_ticker_ids:
        # Close the open period at yesterday so today's `as_of=today`
        # query already shows the removal.  Using today would create a
        # zero-length-membership ambiguity.
        membership = had_by_ticker_id[ticker_id]
        membership.valid_to = today
        n_removed += 1

    n_kept = len(had_ticker_ids & now_ticker_ids)
    log.info(
        "writers.membership_synced",
        index_code=index_code,
        kept=n_kept,
        added=n_added,
        removed=n_removed,
    )
    return (n_kept, n_added, n_removed)


__all__: list[str] = [
    "resolve_or_create_ticker",
    "sync_current_memberships",
    "upsert_ohlcv_rows",
]
