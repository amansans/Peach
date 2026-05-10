"""Seed reference tables: exchanges, GICS sectors, and tracked indices.

This script is *idempotent*: running it multiple times leaves the database
in the same state as running it once.  Each row is upserted by its natural
key (`code` column).  No row is ever deleted by this script — to remove a
row, do so via a migration so the change is tracked.

Usage
-----
    uv run python -m scripts.bootstrap_universe
    make seed                                   # equivalent shortcut

What this seeds
---------------
1.  **Exchanges** — XNAS, XNYS, ARCA, BATS.  Enough to classify every
    SP500 / NDX / DJI ticker.

2.  **GICS sectors** — the 11 top-level GICS sectors with their official
    codes.  Industry-group / industry / sub-industry rows are seeded in
    Phase 1 when we ingest tickers; for Phase 0 the 11 sectors are
    sufficient and keep this script focused.

3.  **Indices** — SP500, NDX, DJI with their issuer-ETF provider hint so
    Phase 1's membership ingestion knows where to pull the daily holdings
    CSV from.

The GICS classification system is jointly maintained by S&P Global and
MSCI; codes are stable and have been since 1999.  Reference:
https://www.msci.com/our-solutions/indexes/gics
"""

from __future__ import annotations

import structlog
import typer
from sqlalchemy import select

from peach.db.models import Exchange, Index, Sector
from peach.db.session import session_scope

# Structlog logger — JSON output by default at process top-level.
log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
# Hard-coded here rather than in YAML because (a) it is genuinely static
# (changes ~once per decade), and (b) keeping it in Python lets the script
# remain dependency-free of the yaml-loading layer.
# ---------------------------------------------------------------------------

# The exchanges that host all SP500 / NDX / DJI tickers.  MIC codes per ISO
# 10383; "BATS" is the legacy code for Cboe BZX which hosts a handful of
# Berkshire-class names.
EXCHANGES: list[tuple[str, str]] = [
    ("XNAS", "NASDAQ Stock Market"),
    ("XNYS", "New York Stock Exchange"),
    ("ARCX", "NYSE Arca"),
    ("BATS", "Cboe BZX Exchange"),
]


# The 11 top-level GICS sectors.  Codes are 2-digit per the GICS spec —
# stored as strings to preserve any leading zeros (none currently but the
# spec allows them at lower levels).
GICS_SECTORS: list[tuple[str, str]] = [
    ("10", "Energy"),
    ("15", "Materials"),
    ("20", "Industrials"),
    ("25", "Consumer Discretionary"),
    ("30", "Consumer Staples"),
    ("35", "Health Care"),
    ("40", "Financials"),
    ("45", "Information Technology"),
    ("50", "Communication Services"),
    ("55", "Utilities"),
    ("60", "Real Estate"),
]


# Indices to track.  `provider` records which issuer's daily holdings CSV
# we'll lean on as the ongoing ground truth for membership in Phase 1.
#
# * SP500 — historical membership comes from Wikipedia revision parsing;
#   ongoing tracking from BlackRock's IVV holdings CSV.
# * NDX — Invesco publishes daily QQQ holdings CSVs.
# * DJI — historical membership from Wikipedia; ongoing from BlackRock's
#   DIA holdings CSV.
INDICES: list[tuple[str, str, str]] = [
    ("SP500", "S&P 500", "ishares"),
    ("NDX", "Nasdaq-100", "invesco"),
    ("DJI", "Dow Jones Industrial Average", "ishares"),
]


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------
# Wrapped in a Typer app even though there's only one command, because:
# (a) consistency across our scripts/, and
# (b) free `--help` output that documents options as we add them.
# ---------------------------------------------------------------------------
app = typer.Typer(add_completion=False, help=__doc__)


def _upsert_exchanges() -> int:
    """Insert any missing exchange rows.  Returns the number inserted."""
    inserted = 0
    with session_scope() as session:
        existing_codes = set(session.scalars(select(Exchange.code)).all())
        for code, name in EXCHANGES:
            if code in existing_codes:
                continue
            session.add(Exchange(code=code, name=name))
            inserted += 1
    return inserted


def _upsert_sectors() -> int:
    """Insert any missing top-level GICS sector rows.  Returns count inserted.

    Top-level sectors have `level=1` and `parent_id=NULL`.  Industry-group
    and lower levels are seeded in Phase 1 alongside ticker ingestion.
    """
    inserted = 0
    with session_scope() as session:
        existing_codes = set(session.scalars(select(Sector.code)).all())
        for code, name in GICS_SECTORS:
            if code in existing_codes:
                continue
            session.add(Sector(code=code, name=name, level=1, parent_id=None))
            inserted += 1
    return inserted


def _upsert_indices() -> int:
    """Insert any missing tracked-index rows.  Returns count inserted."""
    inserted = 0
    with session_scope() as session:
        existing_codes = set(session.scalars(select(Index.code)).all())
        for code, name, provider in INDICES:
            if code in existing_codes:
                continue
            session.add(Index(code=code, name=name, provider=provider))
            inserted += 1
    return inserted


@app.command()
def main() -> None:
    """Run all three seed steps in dependency order.

    Sectors have no FK dependencies on the others.  Tickers (created later)
    FK to both exchanges and sectors, so seeding both first means later
    runs can immediately reference them by code.
    """
    log.info("bootstrap.start")

    n_exchanges = _upsert_exchanges()
    log.info("bootstrap.exchanges_done", inserted=n_exchanges, total_known=len(EXCHANGES))

    n_sectors = _upsert_sectors()
    log.info("bootstrap.sectors_done", inserted=n_sectors, total_known=len(GICS_SECTORS))

    n_indices = _upsert_indices()
    log.info("bootstrap.indices_done", inserted=n_indices, total_known=len(INDICES))

    # Final summary line — easy to grep in cron logs ("bootstrap.complete").
    log.info(
        "bootstrap.complete",
        exchanges_inserted=n_exchanges,
        sectors_inserted=n_sectors,
        indices_inserted=n_indices,
    )


if __name__ == "__main__":
    app()
