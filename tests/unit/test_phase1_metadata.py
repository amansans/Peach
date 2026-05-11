"""Phase 1 smoke tests — metadata registration and import-graph health."""

from __future__ import annotations

from peach.db.base import Base
from peach.db.models import (
    CorporateAction,
    IndexMembership,
    OHLCVDaily,
)


def test_phase1_models_registered_with_metadata() -> None:
    """The three Phase 1 tables must be visible to Alembic's autogenerate.

    Mirrors the Phase 0 invariant — guards against the failure mode where
    a model is defined but never imported.
    """
    expected = {"index_memberships", "ohlcv_daily", "corporate_actions"}
    missing = expected - set(Base.metadata.tables.keys())
    assert not missing, f"Phase 1 models defined but unregistered: {missing}"

    # And the classes themselves are importable from the package root.
    assert IndexMembership.__tablename__ == "index_memberships"
    assert OHLCVDaily.__tablename__ == "ohlcv_daily"
    assert CorporateAction.__tablename__ == "corporate_actions"


def test_ingestion_package_imports() -> None:
    """The ingestion sub-package and its sources import cleanly.

    This catches circular-import regressions and missing transitive
    dependencies before they hit a daily-EOD run.
    """
    from peach.ingestion import orchestrator, writers  # noqa: F401
    from peach.ingestion.sources import (  # noqa: F401
        issuer_csv_membership,
        stooq_source,
        wikipedia_membership,
        yfinance_source,
    )
