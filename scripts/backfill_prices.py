"""One-shot OHLCV backfill driver.

Used after a fresh ``alembic upgrade head`` + ``make seed`` +
``daily_eod --backfill-days=1`` to populate the 5-year historical window
the architectural plan calls for.

Why a separate script rather than a `daily_eod` flag?  The 5-year backfill
takes ~30 minutes (530 tickers x 1 HTTP call per ticker, 1 req/sec polite
limit) and we want it isolated from the daily routine — running it twice
should be a deliberate choice, not a typo.

Usage
-----
::

    uv run python -m scripts.backfill_prices --years 5
    uv run python -m scripts.backfill_prices --years 5 --only-symbol AAPL

The ``--only-symbol`` flag is for ad-hoc remediation of a single ticker
whose history got corrupted or partially-ingested.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Annotated

import structlog
import typer
from sqlalchemy import select

from peach.db.base import utcnow
from peach.db.models.membership import IndexMembership
from peach.db.models.reference import Index, Ticker
from peach.db.session import session_scope
from peach.ingestion.orchestrator import ingest_prices_for_tickers

log = structlog.get_logger(__name__)

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    years: Annotated[
        int,
        typer.Option("--years", "-y", help="How many years of history to backfill (default 5)."),
    ] = 5,
    only_symbol: Annotated[
        str | None,
        typer.Option(
            "--only-symbol",
            help="If set, backfill ONLY this symbol.  Useful for ad-hoc fixes.",
        ),
    ] = None,
    sleep_between: Annotated[
        float,
        typer.Option(
            "--sleep-between",
            help=(
                "Seconds to sleep between symbols.  Stooq's polite limit is "
                "~1 req/sec; the default of 1.0 keeps us comfortably inside."
            ),
        ),
    ] = 1.0,
) -> None:
    """Drive a multi-year OHLCV backfill across the current SP500/NDX/DJI universe.

    Picks symbols from `index_memberships` open-ended rows so freshly-added
    tickers are included.  Per-symbol failures don't abort the run; the
    orchestrator absorbs them.
    """
    today = utcnow().date()
    start = today - timedelta(days=365 * years)
    log.info(
        "backfill.start",
        start=str(start),
        end=str(today),
        years=years,
        only_symbol=only_symbol,
    )

    if only_symbol:
        symbols = [only_symbol]
    else:
        with session_scope() as session:
            rows = session.execute(
                select(Ticker.symbol)
                .join(IndexMembership, IndexMembership.ticker_id == Ticker.id)
                .join(Index, IndexMembership.index_id == Index.id)
                .where(IndexMembership.valid_to.is_(None))
                .distinct()
                .order_by(Ticker.symbol)
            ).all()
            symbols = [r[0] for r in rows]

    if not symbols:
        log.error("backfill.no_symbols")
        return

    log.info("backfill.symbols_loaded", n=len(symbols))

    # We intentionally call the orchestrator one symbol at a time so the
    # sleep-between-symbols throttle works.  The orchestrator's internal
    # loop is fine for daily-EOD (7-day window, polite per ticker) but
    # too aggressive for a 5-year multi-MB-per-ticker pull.
    total_rows = 0
    for i, symbol in enumerate(symbols, start=1):
        result = ingest_prices_for_tickers([symbol], start=start, end=today)
        total_rows += sum(result.values())
        if i % 25 == 0:
            log.info(
                "backfill.progress",
                completed=i,
                of=len(symbols),
                rows_so_far=total_rows,
            )
        if sleep_between > 0:
            time.sleep(sleep_between)

    log.info(
        "backfill.complete",
        n_symbols=len(symbols),
        n_rows=total_rows,
    )


if __name__ == "__main__":
    app()
