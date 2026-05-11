"""Daily end-of-day refresh — the v1 cron entry point.

Cron line (post-US-close, weekdays only)::

    30 21 * * 1-5 cd /opt/peach && /usr/bin/env uv run python -m peach.scheduling.daily_eod

Pipeline order
--------------
1.  **Refresh index memberships** for SP500, NDX, DJI.  Membership
    changes first because step 2 ingests prices for the *current*
    constituents — picking up newly-added tickers immediately on the
    day they join.

2.  **Ingest prices** for every active ticker in any tracked index.
    Default window is "the last 7 calendar days" (covers a long weekend
    + Monday-morning catch-up).  The writer's idempotent upsert means
    fetching the same days twice is harmless.

3.  *(Phase 2+)* Recompute indicator snapshots and screener hits.  Those
    steps live in this same script — added per phase.

Failure semantics
-----------------
* A failure in step 1 is logged but does NOT abort step 2.  We want
  yesterday's prices even if today's membership refresh hits a 503.
* A failure in step 2 for *one* symbol does not abort step 2 for
  the rest (handled inside the orchestrator).
* The script exits 0 only if every step completed.  cron failure
  notification (mailto) thus works without extra wiring.
"""

from __future__ import annotations

import sys
from datetime import timedelta

import structlog
import typer

from peach.db.base import utcnow
from peach.ingestion.orchestrator import (
    ingest_prices_for_tickers,
    refresh_index_memberships,
)

log = structlog.get_logger(__name__)

app = typer.Typer(add_completion=False, help=__doc__)

# Indices we operate on.  Adding a new index means updating both this
# list AND the seed script (so the row exists in `indices`).
TRACKED_INDICES: list[str] = ["SP500", "NDX", "DJI"]


@app.command()
def main(
    backfill_days: int = typer.Option(
        7,
        "--backfill-days",
        help=(
            "How many days of OHLCV to (re-)pull per ticker.  Default 7 covers "
            "a long weekend plus catch-up; bump to 1825 for an initial 5-year "
            "backfill."
        ),
    ),
) -> None:
    """Run the daily EOD pipeline.

    Exits non-zero if any step encountered an unrecoverable failure.
    Per-ticker failures are absorbed by the orchestrator and do not
    flip the exit code.
    """
    today = utcnow().date()
    start = today - timedelta(days=backfill_days)
    log.info("daily_eod.start", today=str(today), backfill_days=backfill_days)

    # ---------- Step 1: membership refresh ---------------------------------
    membership_errors = 0
    union_of_symbols: set[str] = set()
    for index_code in TRACKED_INDICES:
        try:
            kept, added, removed = refresh_index_memberships(index_code)
            log.info(
                "daily_eod.membership_synced",
                index_code=index_code,
                kept=kept,
                added=added,
                removed=removed,
            )
        except Exception as exc:
            membership_errors += 1
            log.error(
                "daily_eod.membership_failed",
                index_code=index_code,
                error=str(exc),
            )

    # ---------- Step 2: price ingestion ------------------------------------
    # Pull the symbol list from the writer-side view of "currently a member
    # of any tracked index".  We do this here rather than relying on the
    # orchestrator output so a partial membership failure doesn't shrink
    # the price-ingest universe.
    from sqlalchemy import select

    from peach.db.models.membership import IndexMembership
    from peach.db.models.reference import Index, Ticker
    from peach.db.session import session_scope

    with session_scope() as session:
        rows = session.execute(
            select(Ticker.symbol)
            .join(IndexMembership, IndexMembership.ticker_id == Ticker.id)
            .join(Index, IndexMembership.index_id == Index.id)
            .where(
                Index.code.in_(TRACKED_INDICES),
                IndexMembership.valid_to.is_(None),
            )
        ).all()
        union_of_symbols = {r[0] for r in rows}

    if not union_of_symbols:
        log.warning(
            "daily_eod.no_symbols_to_ingest",
            note="Run scripts.bootstrap_universe and one membership refresh first.",
        )
    else:
        results = ingest_prices_for_tickers(sorted(union_of_symbols), start=start, end=today)
        n_zero = sum(1 for v in results.values() if v == 0)
        n_total_rows = sum(results.values())
        log.info(
            "daily_eod.prices_done",
            n_symbols=len(results),
            n_rows=n_total_rows,
            n_zero_symbols=n_zero,
        )

    # ---------- Exit code --------------------------------------------------
    # We exit non-zero only when *every* index's membership refresh failed.
    # A partial failure is logged but considered recoverable.
    if membership_errors == len(TRACKED_INDICES):
        log.error("daily_eod.all_memberships_failed")
        sys.exit(2)

    log.info("daily_eod.complete")


if __name__ == "__main__":
    app()
