"""Phase 1 schema: index_memberships, ohlcv_daily, corporate_actions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11

Adds the three Phase 1 tables:

* ``index_memberships`` — bitemporal membership (`valid_from`, `valid_to`)
  per (index, ticker).  The natural-key index on
  ``(index_id, valid_from, valid_to)`` is what membership-as-of queries
  actually hit; the per-column FK indices are for join performance and
  cascade enforcement.

* ``ohlcv_daily`` — daily OHLCV bars.  Composite PK
  ``(ticker_id, bar_date)`` is the clustered layout.  A BRIN index on
  ``bar_date`` accelerates cross-sectional queries — the perfect index
  type for monotonically time-ordered tables (a B-tree on ~700 k rows
  works too, but BRIN uses ~1000× less disk).

* ``corporate_actions`` — splits, dividends, spin-offs.  CHECK constraint
  pins the currently supported ``kind`` set.

Written by hand rather than autogenerate so the BRIN index decision and
CHECK constraint are visible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the three Phase 1 tables and their indices."""

    # -----------------------------------------------------------------------
    # index_memberships
    # -----------------------------------------------------------------------
    op.create_table(
        "index_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "index_id",
            sa.Integer(),
            sa.ForeignKey(
                "indices.id",
                ondelete="RESTRICT",
                name="fk_index_memberships_index_id_indices",
            ),
            nullable=False,
        ),
        sa.Column(
            "ticker_id",
            sa.Integer(),
            sa.ForeignKey(
                "tickers.id",
                ondelete="CASCADE",
                name="fk_index_memberships_ticker_id_tickers",
            ),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
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
        # Natural-key uniqueness — see model docstring for why
        # (index_id, ticker_id) alone isn't unique (re-additions).
        sa.UniqueConstraint(
            "index_id",
            "ticker_id",
            "valid_from",
            name="period_per_index_ticker",
        ),
        # valid_to >= valid_from when not NULL.
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="period_ordered",
        ),
    )
    # FK-side indices for join performance.
    op.create_index(
        "ix_index_memberships_index_id",
        "index_memberships",
        ["index_id"],
    )
    op.create_index(
        "ix_index_memberships_ticker_id",
        "index_memberships",
        ["ticker_id"],
    )
    # The composite index that membership-as-of-T queries actually hit.
    # Postgres can use this for range scans on `valid_from <= T AND
    # (valid_to IS NULL OR valid_to >= T)` filtered by `index_id`.
    op.create_index(
        "ix_index_memberships_index_id_valid_from_valid_to",
        "index_memberships",
        ["index_id", "valid_from", "valid_to"],
    )

    # -----------------------------------------------------------------------
    # ohlcv_daily
    # -----------------------------------------------------------------------
    op.create_table(
        "ohlcv_daily",
        sa.Column(
            "ticker_id",
            sa.Integer(),
            sa.ForeignKey(
                "tickers.id",
                ondelete="CASCADE",
                name="fk_ohlcv_daily_ticker_id_tickers",
            ),
            primary_key=True,
        ),
        sa.Column("bar_date", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("adj_close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.Numeric(20, 0), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
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
        # Sanity: high >= max(open, close) and low <= min(open, close).
        # Catches the most common bad-row shape that Stooq occasionally
        # emits when it concatenates two adjusted sessions.
        sa.CheckConstraint(
            "high >= GREATEST(open, close, low)",
            name="high_is_highest",
        ),
        sa.CheckConstraint(
            "low <= LEAST(open, close, high)",
            name="low_is_lowest",
        ),
    )
    # BRIN index on bar_date — natural choice for a time-ordered table
    # where rows are inserted in chronological order.  The bitmap index
    # scan over a BRIN is sufficient for cross-section queries like
    # "all closes on 2020-03-23".
    op.execute(
        "CREATE INDEX ix_ohlcv_daily_bar_date_brin "
        "ON ohlcv_daily USING brin (bar_date)"
    )

    # -----------------------------------------------------------------------
    # corporate_actions
    # -----------------------------------------------------------------------
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticker_id",
            sa.Integer(),
            sa.ForeignKey(
                "tickers.id",
                ondelete="CASCADE",
                name="fk_corporate_actions_ticker_id_tickers",
            ),
            nullable=False,
        ),
        sa.Column("action_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "ratio",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="1",
        ),
        sa.Column("cash_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
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
        # Pin the allowed kinds.  Extending this set is a one-line CHECK
        # update in a future migration — much smaller blast radius than
        # ALTER TYPE on a Postgres ENUM.
        sa.CheckConstraint(
            "kind IN ('split', 'dividend', 'spinoff')",
            name="kind_supported",
        ),
        # Ratios are positive non-zero values.  Catches sign-flip and
        # "1/0 reverse split" data errors.
        sa.CheckConstraint("ratio > 0", name="ratio_positive"),
    )
    op.create_index(
        "ix_corporate_actions_ticker_id",
        "corporate_actions",
        ["ticker_id"],
    )
    op.create_index(
        "ix_corporate_actions_action_date",
        "corporate_actions",
        ["action_date"],
    )


def downgrade() -> None:
    """Reverse of :func:`upgrade`.  Drop in reverse FK-dependency order."""
    op.drop_index("ix_corporate_actions_action_date", table_name="corporate_actions")
    op.drop_index("ix_corporate_actions_ticker_id", table_name="corporate_actions")
    op.drop_table("corporate_actions")

    op.execute("DROP INDEX IF EXISTS ix_ohlcv_daily_bar_date_brin")
    op.drop_table("ohlcv_daily")

    op.drop_index(
        "ix_index_memberships_index_id_valid_from_valid_to",
        table_name="index_memberships",
    )
    op.drop_index("ix_index_memberships_ticker_id", table_name="index_memberships")
    op.drop_index("ix_index_memberships_index_id", table_name="index_memberships")
    op.drop_table("index_memberships")
