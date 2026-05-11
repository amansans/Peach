"""Phase 2 schema: indicators_catalog and indicator_snapshots.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11

Adds the two tables Phase 2 indicators write into:

* ``indicators_catalog`` — one row per ``indicator_code`` the engine
  knows how to compute.  Seeded from the in-code registry by
  ``scripts.seed_indicators``.

* ``indicator_snapshots`` — per-bar values, keyed
  ``(ticker_id, bar_date, indicator_code)``.  Composite PK + secondary
  index on ``(indicator_code, bar_date)`` to accelerate cross-sectional
  screener queries ("every ticker where rsi_14 < 30 today").

The FK from ``indicator_snapshots.indicator_code`` to
``indicators_catalog.code`` enforces "we only ever store rows for codes
we've registered".  Deactivating a catalog row (set ``is_active = False``)
preserves historical snapshots without breaking the FK.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the catalog table first, then the snapshot table that FKs to it."""

    # -----------------------------------------------------------------------
    # indicators_catalog
    # -----------------------------------------------------------------------
    op.create_table(
        "indicators_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("component", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        # JSON, not JSONB, because:
        # * the column is small (a dozen integer params at most);
        # * we never query into it from SQL — the catalog is a UI helper;
        # * JSON preserves insertion order which makes diffs friendlier.
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_indicators_catalog_code"),
    )
    op.create_index("ix_indicators_catalog_code", "indicators_catalog", ["code"])
    op.create_index("ix_indicators_catalog_family", "indicators_catalog", ["family"])
    op.create_index("ix_indicators_catalog_category", "indicators_catalog", ["category"])

    # -----------------------------------------------------------------------
    # indicator_snapshots
    # -----------------------------------------------------------------------
    op.create_table(
        "indicator_snapshots",
        sa.Column(
            "ticker_id",
            sa.Integer(),
            sa.ForeignKey(
                "tickers.id",
                ondelete="CASCADE",
                name="fk_indicator_snapshots_ticker_id_tickers",
            ),
            primary_key=True,
        ),
        sa.Column("bar_date", sa.Date(), primary_key=True),
        sa.Column(
            "indicator_code",
            sa.String(length=64),
            sa.ForeignKey(
                "indicators_catalog.code",
                ondelete="CASCADE",
                name="fk_indicator_snapshots_indicator_code_indicators_catalog",
            ),
            primary_key=True,
        ),
        # Numeric(28, 12) gives us range for OBV (which can reach ~10^13
        # for the largest names) AND fractional precision for ratios.
        sa.Column("value", sa.Numeric(28, 12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Cross-sectional screener index: "every ticker for which `rsi_14`
    # on `2026-05-08` was < 30" hits this index directly.
    op.create_index(
        "ix_indicator_snapshots_code_date",
        "indicator_snapshots",
        ["indicator_code", "bar_date"],
    )


def downgrade() -> None:
    """Reverse — drop snapshots first (FK target), then the catalog."""
    op.drop_index(
        "ix_indicator_snapshots_code_date",
        table_name="indicator_snapshots",
    )
    op.drop_table("indicator_snapshots")

    op.drop_index("ix_indicators_catalog_category", table_name="indicators_catalog")
    op.drop_index("ix_indicators_catalog_family", table_name="indicators_catalog")
    op.drop_index("ix_indicators_catalog_code", table_name="indicators_catalog")
    op.drop_table("indicators_catalog")
