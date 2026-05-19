"""Seed ``indicators_catalog`` from the in-code registry.

Idempotent: re-running upserts every row (in case the spec's params or
version has changed since the last seed).  Deactivates any catalog
row whose code is no longer registered, preserving its historical
snapshots while marking it inactive.

Usage::

    uv run python -m scripts.seed_indicators
    make seed-indicators                     # equivalent shortcut
"""

from __future__ import annotations

import structlog
import typer
from sqlalchemy import select

from peach.db.models.indicators import IndicatorCatalog
from peach.db.session import session_scope
from peach.indicators.registry import all_specs

log = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main() -> None:
    """Reconcile ``indicators_catalog`` with the in-code registry."""
    specs = all_specs()

    # Expand each spec into one catalog entry per produced code.  A
    # MACD spec produces three (line / signal / hist); the catalog
    # stores one row per code so the UI can group via `family`.
    desired: dict[str, dict[str, object]] = {}
    for spec in specs:
        for code, component in zip(spec.produces, spec.components, strict=True):
            desired[code] = {
                "code": code,
                "family": spec.family,
                "component": component,
                "category": spec.category,
                "params_json": spec.params,
                "version": spec.version,
                "is_active": True,
            }

    with session_scope() as session:
        existing = {row.code: row for row in session.scalars(select(IndicatorCatalog)).all()}

        # Insert or update everything currently registered.
        n_inserted = 0
        n_updated = 0
        for code, fields in desired.items():
            row = existing.get(code)
            if row is None:
                session.add(IndicatorCatalog(**fields))  # type: ignore[arg-type]
                n_inserted += 1
            else:
                changed = False
                for attr, val in fields.items():
                    if getattr(row, attr) != val:
                        setattr(row, attr, val)
                        changed = True
                if changed:
                    n_updated += 1

        # Anything in the DB but no longer registered: deactivate (don't
        # delete — historical snapshots still reference it via FK).
        n_deactivated = 0
        for code, row in existing.items():
            if code not in desired and row.is_active:
                row.is_active = False
                n_deactivated += 1

    log.info(
        "seed_indicators.complete",
        n_inserted=n_inserted,
        n_updated=n_updated,
        n_deactivated=n_deactivated,
        total_in_registry=len(desired),
    )


if __name__ == "__main__":
    app()
