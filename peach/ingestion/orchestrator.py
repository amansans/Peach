"""High-level ingestion entry points.

Two functions are the public surface of this module:

* :func:`refresh_index_memberships` — pull the current constituents of an
  index from the canonical issuer CSV, fall back to Wikipedia if the
  issuer URL fails, and reconcile against `index_memberships`.

* :func:`ingest_prices_for_tickers` — for each ticker, try Stooq first;
  on empty/error result, fall back to yfinance.  Upsert into
  ``ohlcv_daily``.

Both functions are safe to call repeatedly on the same day — the writer
layer's idempotency guarantee carries through.

Why a thin orchestrator and not a single God function?
------------------------------------------------------
The orchestrator concentrates the *policy* (which source first, when to
fall back, when to give up), while the source modules concentrate the
*mechanism* (parsing).  Adding a new source tomorrow (Polygon for
prices, say) is a parser drop-in plus one line of policy change here,
not a rewrite.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import select

from peach.db.models.reference import Exchange, Index, Ticker
from peach.db.session import session_scope
from peach.ingestion.base import ParsedMembership, ParsedOHLCV
from peach.ingestion.sources.issuer_csv_membership import IssuerCsvMembershipSource
from peach.ingestion.sources.stooq_source import StooqSource
from peach.ingestion.sources.wikipedia_membership import WikipediaMembershipSource
from peach.ingestion.sources.yfinance_source import YFinanceSource
from peach.ingestion.writers import sync_current_memberships, upsert_ohlcv_rows

log = structlog.get_logger(__name__)


# Country code → default listing-exchange MIC.  Centralised so the
# choice is in one place and trivially extensible (LSE → XLON, etc.).
_DEFAULT_EXCHANGE_FOR_COUNTRY: dict[str, str] = {
    "US": "XNAS",
    "CA": "XTSE",
}


# ---------------------------------------------------------------------------
# Membership refresh
# ---------------------------------------------------------------------------


def refresh_index_memberships(index_code: str) -> tuple[int, int, int]:
    """Pull current members of ``index_code`` and reconcile the DB state.

    Source priority
    ---------------
    1.  **Issuer CSV** (iShares IVV/DIA, Invesco QQQ) — preferred because
        it's machine-published and updated daily.
    2.  **Wikipedia** — fallback if the issuer URL fails (rate limit,
        format change, network blip).  Wikipedia lags by hours to days
        but provides a reasonable approximation.

    Returns
    -------
    tuple[int, int, int]
        ``(n_kept, n_added, n_removed)`` from the writer-level reconciliation.

    Notes
    -----
    If *both* sources fail, we DO NOT close every open membership period
    — that would silently destroy history.  Instead we log and return
    a tuple of zeros, leaving the schema untouched.  The data-quality
    job in Phase 1's daily flow will flag the missing refresh.
    """
    rows: list[ParsedMembership] = []
    used_source = "none"

    # Try issuer first.  Catch everything because we genuinely want to
    # fall through to Wikipedia on any failure shape.
    try:
        issuer = IssuerCsvMembershipSource()
        rows = list(issuer.fetch_current_members(index_code))
        used_source = "issuer_csv"
    except Exception as exc:
        log.warning(
            "orchestrator.membership.issuer_failed",
            index_code=index_code,
            error=str(exc),
        )

    if not rows:
        try:
            wiki = WikipediaMembershipSource()
            rows = list(wiki.fetch_current_members(index_code))
            used_source = "wikipedia"
        except Exception as exc:
            log.warning(
                "orchestrator.membership.wikipedia_failed",
                index_code=index_code,
                error=str(exc),
            )

    if not rows:
        log.error(
            "orchestrator.membership.no_data",
            index_code=index_code,
        )
        return (0, 0, 0)

    log.info(
        "orchestrator.membership.fetched",
        index_code=index_code,
        source=used_source,
        n=len(rows),
    )

    # Look up the index's listing country so newly-created ticker stubs
    # get the right default exchange (XNAS for US indices, XTSE for TSX).
    with session_scope() as session:
        country = session.scalar(select(Index.country_code).where(Index.code == index_code))
    default_exchange = _DEFAULT_EXCHANGE_FOR_COUNTRY.get(country or "US", "XNAS")

    with session_scope() as session:
        return sync_current_memberships(
            session,
            index_code,
            rows,
            default_exchange_code=default_exchange,
        )


# ---------------------------------------------------------------------------
# Price ingestion
# ---------------------------------------------------------------------------


def _country_for_symbols(symbols: list[str]) -> dict[str, str]:
    """Look up each symbol's listing country (via its exchange) in one query.

    Pre-fetching avoids N+1 round-trips inside the per-symbol loop and
    keeps the orchestrator's main flow readable.  Symbols not yet in the
    ``tickers`` table fall back to ``"US"`` — the safe default for a
    not-yet-curated row (Stooq's ``.us`` suffix is what most US tickers
    use; a CA-only symbol that lands here without a prior membership
    refresh is a rare ordering edge case).
    """
    if not symbols:
        return {}
    with session_scope() as session:
        rows = session.execute(
            select(Ticker.symbol, Exchange.country_code)
            .join(Exchange, Ticker.exchange_id == Exchange.id)
            .where(Ticker.symbol.in_(symbols))
        ).all()
    return {s: c for s, c in rows}


def ingest_prices_for_tickers(symbols: list[str], start: date, end: date) -> dict[str, int]:
    """Backfill or update OHLCV for each symbol in ``[start, end]``.

    For each symbol:

    1.  Try Stooq — primary source per the plan.  URL suffix (``.us`` /
        ``.ca``) is picked from the ticker's listing exchange country.
    2.  If Stooq returns zero rows (the documented "No data" path),
        fall back to yfinance.  yfinance reads the symbol verbatim;
        the ``.TO`` storage suffix for TSX names is already what
        Yahoo expects.
    3.  Upsert the resulting bars.  Errors on individual symbols are
        logged but do not abort the batch — a single ticker failure
        shouldn't sink the daily run.

    Returns
    -------
    dict[str, int]
        ``{symbol: rows_upserted}``.  Symbols that produced zero rows
        from both sources map to ``0``.
    """
    stooq = StooqSource()
    yfin = YFinanceSource()
    results: dict[str, int] = {}
    country_by_symbol = _country_for_symbols(symbols)

    for symbol in symbols:
        country = country_by_symbol.get(symbol, "US")
        try:
            stooq_rows: list[ParsedOHLCV] = list(
                stooq.fetch_ohlcv(symbol, start, end, country_code=country)
            )
        except Exception as exc:
            log.warning(
                "orchestrator.prices.stooq_failed",
                symbol=symbol,
                country=country,
                error=str(exc),
            )
            stooq_rows = []

        if stooq_rows:
            rows = stooq_rows
        else:
            try:
                rows = list(yfin.fetch_ohlcv(symbol, start, end, country_code=country))
            except Exception as exc:
                log.warning(
                    "orchestrator.prices.yfinance_failed",
                    symbol=symbol,
                    country=country,
                    error=str(exc),
                )
                rows = []

        if not rows:
            log.warning("orchestrator.prices.empty", symbol=symbol, country=country)
            results[symbol] = 0
            continue

        with session_scope() as session:
            n = upsert_ohlcv_rows(session, rows)
        results[symbol] = n

    log.info(
        "orchestrator.prices.batch_complete",
        n_symbols=len(symbols),
        n_rows_total=sum(results.values()),
    )
    return results


__all__: list[str] = ["ingest_prices_for_tickers", "refresh_index_memberships"]
